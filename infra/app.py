#!/usr/bin/env python3
"""CDK app for the BIXI demand MLOps platform (Phase 2 infrastructure).

Stacks
  BixiNetwork  VPC (public subnets, no NAT)
  BixiStorage  S3 data + pipeline buckets (+ SSM parameters)
  BixiMlflow   MLflow tracking server on EC2 + S3 artifact store
  BixiBatch    ECR training image + AWS Batch compute + job definition
  BixiServe    FastAPI /predict service on App Runner (ECR image, no VPC)
  BixiUi       FastAPI-backed Streamlit container on EC2

Deploy (with SSO creds):
  export BIXI_ALLOW_CIDR="<your.ip>/32"     # who can reach MLflow :5000 / SSH
  cd infra && cdk deploy BixiNetwork BixiStorage BixiMlflow BixiBatch
  # Run the pipeline, then deploy BixiServe and BixiUi.

Restrict access by passing your IP:  -c allow_cidr=1.2.3.4/32  (default 0.0.0.0/0).
"""

import os

import aws_cdk as cdk

from bixi_infra.batch_stack import BatchStack
from bixi_infra.mlflow_stack import MlflowStack
from bixi_infra.network_stack import NetworkStack
from bixi_infra.serve_stack import ServeStack
from bixi_infra.storage_stack import StorageStack
from bixi_infra.ui_stack import UiStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-2"),
)

allow_cidr = (app.node.try_get_context("allow_cidr")
              or os.getenv("BIXI_ALLOW_CIDR", "127.0.0.1/32"))
ui_cidr = (app.node.try_get_context("ui_cidr")
           or os.getenv("BIXI_UI_CIDR", "0.0.0.0/0"))
run_id = (app.node.try_get_context("run_id")
          or os.getenv("BIXI_RUN_ID", "cloud-2024"))
repo_ref = (app.node.try_get_context("repo_ref")
            or os.getenv("BIXI_REPO_REF", "main"))
deployment_id = (app.node.try_get_context("deployment_id")
                 or os.getenv("BIXI_DEPLOYMENT_ID", "initial"))

network = NetworkStack(app, "BixiNetwork", env=env)
storage = StorageStack(app, "BixiStorage", env=env)
mlflow = MlflowStack(app, "BixiMlflow", vpc=network.vpc,
                     artifact_bucket=storage.bucket, allow_cidr=allow_cidr, env=env)
batch = BatchStack(app, "BixiBatch", vpc=network.vpc,
                   pipeline_bucket=storage.pipeline_bucket,
                   data_bucket=storage.data_bucket, run_id=run_id, env=env)
serve = ServeStack(app, "BixiServe", pipeline_bucket=storage.bucket,
                   data_bucket=storage.data_bucket, run_id=run_id, env=env)
ui = UiStack(app, "BixiUi", vpc=network.vpc, api_url=serve.service_url,
             api_key_secret=serve.api_key_secret, allow_cidr=ui_cidr,
             repo_ref=repo_ref, deployment_id=deployment_id, env=env)

mlflow.add_dependency(network)
mlflow.add_dependency(storage)
batch.add_dependency(network)
batch.add_dependency(storage)
serve.add_dependency(storage)
ui.add_dependency(network)
ui.add_dependency(serve)

app.synth()
