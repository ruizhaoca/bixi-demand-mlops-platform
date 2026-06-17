"""MLflow tracking server on a small EC2 instance, backed by S3 for artifacts.

* SQLite backend store on the instance (sufficient for the course; survives
  restarts on the root EBS volume).
* Artifacts in the pipeline S3 bucket (``s3://<bucket>/mlflow``).
* Reachable on :5000 from the team CIDR (browser/local training) and from inside
  the VPC (Batch jobs). Elastic IP gives a stable public URL.

The internal URL (private DNS) is published to SSM ``/bixi/mlflow-tracking-uri``
for Batch jobs; the public URL is a stack output for humans.
"""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class MlflowStack(Stack):
    def __init__(self, scope: Construct, cid: str, *, vpc: ec2.IVpc,
                 artifact_bucket: s3.IBucket, allow_cidr: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        sg = ec2.SecurityGroup(self, "MlflowSg", vpc=vpc,
                               description="MLflow server", allow_all_outbound=True)
        sg.add_ingress_rule(ec2.Peer.ipv4(allow_cidr), ec2.Port.tcp(5000), "MLflow UI/API")
        sg.add_ingress_rule(ec2.Peer.ipv4(allow_cidr), ec2.Port.tcp(22), "SSH")
        sg.add_ingress_rule(ec2.Peer.ipv4(vpc.vpc_cidr_block), ec2.Port.tcp(5000),
                            "MLflow from inside VPC (Batch)")

        role = iam.Role(self, "MlflowRole",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                            "AmazonSSMManagedInstanceCore")])
        artifact_bucket.grant_read_write(role)

        # We run MLflow 2.x (stable classic UI). Install python3.11 and bootstrap
        # pip via ensurepip (no reliance on a python3.11-pip package). A swapfile
        # avoids pip OOM. We do NOT `set -e`
        # so a hiccup never silently aborts the rest, and we upload the bootstrap
        # log + listening-ports + service status to S3 for out-of-band debugging
        # (no SSH key / SSM RunCommand is restricted in this account).
        bkt = artifact_bucket.bucket_name
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -x",
            "dnf install -y python3.11",
            "python3.11 -m ensurepip --upgrade || dnf install -y python3.11-pip",
            "fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048",
            "chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile",
            "python3.11 -m pip install --upgrade pip",
            "python3.11 -m pip install --no-cache-dir 'mlflow==2.22.0' boto3",
            "mkdir -p /opt/mlflow",
            "cat >/etc/systemd/system/mlflow.service <<'EOF'",
            "[Unit]",
            "Description=MLflow Tracking Server",
            "After=network-online.target",
            "Wants=network-online.target",
            "[Service]",
            "Environment=AWS_DEFAULT_REGION=" + self.region,
            # MLflow 3.x validates the Host header (DNS-rebinding guard); '*' lets
            # Batch clients reach it via private DNS. Network is locked down by SG.
            "Environment=MLFLOW_SERVER_ALLOWED_HOSTS=*",
            "ExecStart=/bin/bash -lc 'PATH=/usr/local/bin:/usr/bin:$PATH exec python3.11 -m mlflow server "
            "--backend-store-uri sqlite:////opt/mlflow/mlflow.db "
            f"--default-artifact-root s3://{bkt}/mlflow "
            "--host 0.0.0.0 --port 5000'",
            "Restart=always",
            "RestartSec=5",
            "User=root",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOF",
            "systemctl daemon-reload",
            "systemctl enable --now mlflow",
            "sleep 25",
            "ss -tlnp > /tmp/ports.txt 2>&1 || true",
            "systemctl status mlflow --no-pager > /tmp/svc.txt 2>&1 || true",
            "python3.11 -c \"import boto3; b='" + bkt + "'; "
            "[boto3.client('s3').upload_file(f, b, 'mlflow-bootstrap/'+f.split('/')[-1]) "
            "for f in ['/var/log/cloud-init-output.log','/tmp/ports.txt','/tmp/svc.txt']]\" || true",
        )

        instance = ec2.Instance(
            self, "MlflowInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            security_group=sg,
            role=role,
            user_data=user_data,
            user_data_causes_replacement=True,
            block_devices=[ec2.BlockDevice(
                device_name="/dev/xvda",
                volume=ec2.BlockDeviceVolume.ebs(20))],
        )

        eip = ec2.CfnEIP(self, "MlflowEip")
        ec2.CfnEIPAssociation(self, "MlflowEipAssoc",
                              allocation_id=eip.attr_allocation_id,
                              instance_id=instance.instance_id)

        internal_uri = f"http://{instance.instance_private_dns_name}:5000"
        ssm.StringParameter(self, "MlflowUriParam",
                            parameter_name="/bixi/mlflow-tracking-uri",
                            string_value=internal_uri)

        self.public_url = f"http://{eip.attr_public_ip}:5000"
        CfnOutput(self, "MlflowPublicUrl", value=self.public_url)
        CfnOutput(self, "MlflowInternalUri", value=internal_uri)
