#!/usr/bin/env python3
"""CDK app for the BIXI demand MLOps platform (Phase 2 infrastructure).

Stacks
  BixiNetwork  VPC (public subnets, no NAT)
  BixiStorage  S3 bucket for checkpoints / artifacts / reports (+ SSM param)
  BixiMlflow   MLflow tracking server on EC2 + S3 artifact store
  BixiBatch    ECR training image + AWS Batch compute + job definition
  BixiServe    FastAPI /predict service on App Runner (ECR image, no VPC)

Deploy (with SSO creds):
  export BIXI_ALLOW_CIDR="<your.ip>/32"     # who can reach MLflow :5000 / SSH
  cd infra && cdk deploy --all

Restrict access by passing your IP:  -c allow_cidr=1.2.3.4/32  (default 0.0.0.0/0).
"""

import os

import aws_cdk as cdk

from bixi_infra.batch_stack import BatchStack
from bixi_infra.mlflow_stack import MlflowStack
from bixi_infra.network_stack import NetworkStack
from bixi_infra.serve_stack import ServeStack
from bixi_infra.storage_stack import StorageStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-2"),
)

allow_cidr = (app.node.try_get_context("allow_cidr")
              or os.getenv("BIXI_ALLOW_CIDR", "0.0.0.0/0"))
data_bucket = (app.node.try_get_context("data_bucket")
               or os.getenv("BIXI_DATA_BUCKET", "insy684"))

network = NetworkStack(app, "BixiNetwork", env=env)
storage = StorageStack(app, "BixiStorage", env=env)
mlflow = MlflowStack(app, "BixiMlflow", vpc=network.vpc,
                     artifact_bucket=storage.bucket, allow_cidr=allow_cidr, env=env)
batch = BatchStack(app, "BixiBatch", vpc=network.vpc,
                   pipeline_bucket=storage.bucket, data_bucket_name=data_bucket, env=env)
serve = ServeStack(app, "BixiServe", pipeline_bucket=storage.bucket,
                   data_bucket_name=data_bucket, env=env)

mlflow.add_dependency(network)
mlflow.add_dependency(storage)
batch.add_dependency(network)
batch.add_dependency(storage)
serve.add_dependency(storage)

app.synth()
