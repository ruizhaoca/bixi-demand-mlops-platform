"""CDK-managed S3 storage for a reproducible, from-scratch deployment.

The data bucket stores downloaded raw trips/weather, cleaned demand tables,
feature tables, and serving baselines. The pipeline bucket stores checkpoints,
models, MLflow artifacts, and monitoring reports. Both are intentionally removed
by ``cdk destroy`` so a later deployment must rebuild them from public sources.
"""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs) -> None:
        super().__init__(scope, cid, **kwargs)

        common = dict(
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        self.data_bucket = s3.Bucket(
            self,
            "DataBucket",
            **common,
        )
        self.pipeline_bucket = s3.Bucket(
            self,
            "PipelineBucket",
            **common,
        )
        # Backward-compatible alias used by the MLflow stack and older helpers.
        self.bucket = self.pipeline_bucket

        ssm.StringParameter(
            self,
            "DataBucketParam",
            parameter_name="/bixi/data-bucket",
            string_value=self.data_bucket.bucket_name,
        )

        ssm.StringParameter(
            self,
            "PipelineBucketParam",
            parameter_name="/bixi/pipeline-bucket",
            string_value=self.pipeline_bucket.bucket_name,
        )
        CfnOutput(self, "DataBucketName", value=self.data_bucket.bucket_name)
        CfnOutput(self, "PipelineBucketName", value=self.pipeline_bucket.bucket_name)
