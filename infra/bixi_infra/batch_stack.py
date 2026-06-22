"""AWS Batch compute for cloud training, plus the pipeline container image.

* The training image is built from ``docker/Dockerfile.train`` and pushed to ECR
  by CDK at deploy time (DockerImageAsset).
* A managed EC2 Batch compute environment spins a right-sized C/M/R instance up
  for each job and tears it down afterwards (pay-per-use, fast).
* One job definition runs ``python -m bixi.pipeline``; the command (stage flags,
  run id, target) is overridden per submission, so the same definition runs the
  whole pipeline or resumes from any step.
"""

import os

from aws_cdk import CfnOutput, Size, Stack
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_ecr_assets import DockerImageAsset, Platform
from constructs import Construct

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class BatchStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, vpc: ec2.IVpc,
                 pipeline_bucket: s3.IBucket, data_bucket: s3.IBucket,
                 run_id: str = "cloud-2024",
                 **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        image = DockerImageAsset(
            self, "TrainImage",
            directory=REPO_ROOT,
            file="docker/Dockerfile.train",
            platform=Platform.LINUX_AMD64,
        )

        sg = ec2.SecurityGroup(self, "BatchSg", vpc=vpc, allow_all_outbound=True,
                               description="BIXI Batch compute")

        compute_env = batch.ManagedEc2EcsComputeEnvironment(
            self, "ComputeEnv",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            minv_cpus=0,
            maxv_cpus=64,
            use_optimal_instance_classes=True,   # C / M / R families
            spot=False,
            security_groups=[sg],
        )
        queue = batch.JobQueue(self, "JobQueue", priority=1)
        queue.add_compute_environment(compute_env, 1)

        # The from-scratch stages download and materialize raw/clean/feature data.
        job_role = iam.Role(self, "JobRole",
                            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"))
        pipeline_bucket.grant_read_write(job_role)
        data_bucket.grant_read_write(job_role)
        job_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/bixi/*"]))

        container = batch.EcsEc2ContainerDefinition(
            self, "Container",
            image=ecs.ContainerImage.from_docker_image_asset(image),
            cpu=16,
            memory=Size.mebibytes(48000),
            job_role=job_role,
            command=["--from", "ingest", "--targets", "both", "--run-id", run_id,
                     "--n-trials", "40"],
            environment={
                "BIXI_PIPELINE_BUCKET": pipeline_bucket.bucket_name,
                "BIXI_DATA_BUCKET": data_bucket.bucket_name,
                "BIXI_RUN_ID": run_id,
                "AWS_REGION": self.region,
                "AWS_DEFAULT_REGION": self.region,
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="bixi-pipeline"),
        )
        job_def = batch.EcsJobDefinition(
            self, "JobDef", container=container, job_definition_name="bixi-pipeline")

        CfnOutput(self, "JobQueueName", value=queue.job_queue_name)
        CfnOutput(self, "JobDefinitionName", value=job_def.job_definition_name)
        CfnOutput(self, "TrainImageUri", value=image.image_uri)
