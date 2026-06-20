"""App Runner serving tier for the BIXI demand FastAPI service.

This is the third serving surface (alongside the two Streamlit deployments): the
``api/`` FastAPI app, containerized via ``docker/Dockerfile.api`` and run on
**AWS App Runner** — no VPC needed (App Runner reaches S3 over the public AWS
API). Mirrors the ``DockerImageAsset`` + IAM + ``CfnOutput`` pattern in
``batch_stack.py``.

We use the **L1** ``aws_apprunner.CfnService`` (stable, in ``aws-cdk-lib``, no
extra dependency) rather than the alpha L2 construct.

Two roles, least privilege:
* **access role** (``build.apprunner.amazonaws.com``) — pull the image from ECR.
* **instance role** (``tasks.apprunner.amazonaws.com``) — read the pipeline +
  data buckets and ``/bixi/*`` SSM params, for ``s3`` serving mode at runtime.
"""

import os

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_apprunner as apprunner
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_ecr_assets import DockerImageAsset, Platform
from constructs import Construct

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class ServeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        cid: str,
        *,
        pipeline_bucket: s3.IBucket,
        data_bucket_name: str = "insy684",
        run_id: str = "cloud-2024",
        **kwargs,
    ) -> None:
        super().__init__(scope, cid, **kwargs)

        image = DockerImageAsset(
            self,
            "ApiImage",
            directory=REPO_ROOT,
            file="docker/Dockerfile.api",
            platform=Platform.LINUX_AMD64,
        )

        # Role App Runner assumes to pull the image from ECR.
        access_role = iam.Role(
            self,
            "AccessRole",
            assumed_by=iam.ServicePrincipal("build.apprunner.amazonaws.com"),
        )
        image.repository.grant_pull(access_role)

        # Role the running container assumes (for `s3` serving mode at runtime).
        instance_role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("tasks.apprunner.amazonaws.com"),
        )
        pipeline_bucket.grant_read(instance_role)
        data_bucket = s3.Bucket.from_bucket_name(self, "DataBucket", data_bucket_name)
        data_bucket.grant_read(instance_role)
        instance_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/bixi/*"],
            )
        )

        runtime_env = {
            "BIXI_SERVING_MODE": "s3",
            "BIXI_RUN_ID": run_id,
            "BIXI_PIPELINE_BUCKET": pipeline_bucket.bucket_name,
            "BIXI_DATA_BUCKET": data_bucket_name,
            "AWS_REGION": self.region,
        }
        env_pairs = [
            apprunner.CfnService.KeyValuePairProperty(name=key, value=value)
            for key, value in runtime_env.items()
        ]

        service = apprunner.CfnService(
            self,
            "Service",
            service_name="bixi-api",
            source_configuration=apprunner.CfnService.SourceConfigurationProperty(
                authentication_configuration=apprunner.CfnService.AuthenticationConfigurationProperty(
                    access_role_arn=access_role.role_arn,
                ),
                auto_deployments_enabled=False,
                image_repository=apprunner.CfnService.ImageRepositoryProperty(
                    image_identifier=image.image_uri,
                    image_repository_type="ECR",
                    image_configuration=apprunner.CfnService.ImageConfigurationProperty(
                        port="8000",
                        runtime_environment_variables=env_pairs,
                    ),
                ),
            ),
            instance_configuration=apprunner.CfnService.InstanceConfigurationProperty(
                cpu="0.25 vCPU",
                memory="0.5 GB",
                instance_role_arn=instance_role.role_arn,
            ),
            health_check_configuration=apprunner.CfnService.HealthCheckConfigurationProperty(
                protocol="HTTP",
                path="/health",
                interval=10,
                timeout=5,
                healthy_threshold=1,
                unhealthy_threshold=5,
            ),
        )

        CfnOutput(self, "ApiServiceUrl", value=f"https://{service.attr_service_url}")
        CfnOutput(self, "ApiImageUri", value=image.image_uri)
