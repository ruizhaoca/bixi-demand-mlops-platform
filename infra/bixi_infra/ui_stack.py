"""Public EC2 host for the FastAPI-backed Streamlit UI.

The instance is bootstrapped from the repository's ``main`` branch, retrieves the
FastAPI key through its IAM role, and runs the UI in Docker on port 8501. It does
not receive S3 permissions or model artifacts.
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class UiStack(Stack):
    def __init__(
        self,
        scope: Construct,
        cid: str,
        *,
        vpc: ec2.IVpc,
        api_url: str,
        api_key_secret: secretsmanager.ISecret,
        allow_cidr: str = "0.0.0.0/0",
        repo_ref: str = "main",
        deployment_id: str = "initial",
        **kwargs,
    ) -> None:
        super().__init__(scope, cid, **kwargs)

        role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )
        api_key_secret.grant_read(role)

        security_group = ec2.SecurityGroup(
            self,
            "SecurityGroup",
            vpc=vpc,
            allow_all_outbound=True,
            description="Public Streamlit UI",
        )
        security_group.add_ingress_rule(
            ec2.Peer.ipv4(allow_cidr),
            ec2.Port.tcp(8501),
            "Streamlit public endpoint",
        )

        instance = ec2.Instance(
            self,
            "Instance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=role,
            security_group=security_group,
            require_imdsv2=True,
            user_data_causes_replacement=True,
        )

        repo_url = "https://github.com/ruizhaoca/bixi-demand-mlops-platform.git"
        secret_arn = api_key_secret.secret_arn
        instance.user_data.add_commands(
            "set -euo pipefail",
            f"echo 'deployment_id={deployment_id}'",
            "dnf install -y docker git",
            "command -v aws >/dev/null",
            "systemctl enable --now docker",
            "mkdir -p /opt/bixi",
            f"git clone --depth 1 --branch '{repo_ref}' '{repo_url}' /opt/bixi/repo",
            "cd /opt/bixi/repo",
            f"API_KEY=$(aws secretsmanager get-secret-value --region '{self.region}' "
            f"--secret-id '{secret_arn}' --query SecretString --output text)",
            "docker build -f docker/Dockerfile.streamlit_fastapi "
            "-t bixi-streamlit-fastapi .",
            "docker run -d --name bixi-streamlit-fastapi --restart unless-stopped "
            "-p 8501:8501 "
            f"-e BIXI_API_URL='{api_url}' "
            "-e BIXI_API_TIMEOUT=120 "
            "-e BIXI_API_KEY=\"$API_KEY\" "
            "bixi-streamlit-fastapi",
        )

        elastic_ip = ec2.CfnEIP(self, "ElasticIp", domain="vpc")
        ec2.CfnEIPAssociation(
            self,
            "ElasticIpAssociation",
            allocation_id=elastic_ip.attr_allocation_id,
            instance_id=instance.instance_id,
        )

        CfnOutput(self, "InstanceId", value=instance.instance_id)
        CfnOutput(self, "PublicIp", value=elastic_ip.ref)
        CfnOutput(self, "StreamlitUrl", value=f"http://{elastic_ip.ref}:8501")
