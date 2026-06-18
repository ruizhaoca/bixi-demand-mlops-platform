# EC2-Only Streamlit Deployment Guide

This deployment option runs Streamlit directly on an EC2 instance and loads
Phase-2 model artifacts from S3 at runtime.

It is separate from the Streamlit Community Cloud deployment:

- Community Cloud entrypoint: `app.py`
- EC2 entrypoint: `app_ec2.py`

The EC2 version is S3-first and does not use the packaged local artifacts under
`artifacts/streamlit-community-cloud/`.

## Architecture

```text
Browser
  -> EC2 public IP on port 8501
      -> Streamlit container running app_ec2.py
          -> S3 Phase-2 artifacts via EC2 IAM Role
          -> Open-Meteo 15-minute weather forecast API
```

The app keeps loaded model objects in the Streamlit process cache after startup.
If the container restarts, it reads the artifacts from S3 again.

## S3 Artifact Sources

Default model run:

```text
BIXI_RUN_ID=cloud-2024
```

Pipeline bucket:

```text
s3://bixistorage-pipelinebucketb967bd35-icnkid23rfsa/bixi-mlops/runs/cloud-2024/
```

Serving baseline bucket:

```text
s3://insy684/bixi-serving-artifacts/cloud-2024/
```

Required per target, where target is `departure` or `arrival`:

```text
s3://bixistorage-pipelinebucketb967bd35-icnkid23rfsa/bixi-mlops/runs/cloud-2024/<target>/train/best_model.pkl
s3://bixistorage-pipelinebucketb967bd35-icnkid23rfsa/bixi-mlops/runs/cloud-2024/<target>/data/encoder.pkl
s3://insy684/bixi-serving-artifacts/cloud-2024/<target>/serving_baselines.parquet
```

Optional monitoring artifacts:

```text
metrics.json
fairness_report.json
drift_summary.json
registered_model.json
shap_importance.csv
```

## EC2 IAM Role

Do not put AWS access keys in the repo, Docker image, or environment file.

Attach an IAM role to the EC2 instance with read access to the required S3
prefixes. A minimal policy can look like this:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::bixistorage-pipelinebucketb967bd35-icnkid23rfsa/bixi-mlops/runs/cloud-2024/*",
        "arn:aws:s3:::insy684/bixi-serving-artifacts/cloud-2024/*"
      ]
    }
  ]
}
```

If the bucket or run id changes, update the policy and environment variables.

## EC2 Security Group

For a simple class demo, open:

```text
22    from your IP only
8501  from 0.0.0.0/0, or from your IP only for private testing
```

This deployment intentionally skips Route 53, ALB, Nginx, and SSL. The public URL
will be:

```text
http://<EC2-public-ip>:8501
```

An Elastic IP can be attached if you want the IP address to remain stable.

## Build And Run On EC2

Install Docker on the EC2 instance, then clone the repo and checkout this branch:

```bash
git clone https://github.com/ruizhaoca/bixi-demand-mlops-platform.git
cd bixi-demand-mlops-platform
git checkout phase4-streamlit-ec2
```

Run the helper script:

```bash
bash scripts/run_streamlit_ec2_container.sh
```

The script builds:

```text
docker/Dockerfile.streamlit_ec2
```

and starts a container on port `8501`.

## Manual Docker Commands

If you prefer not to use the helper script:

```bash
docker build -f docker/Dockerfile.streamlit_ec2 -t bixi-streamlit-ec2 .

docker run -d \
  --name bixi-streamlit-ec2 \
  --restart unless-stopped \
  -p 8501:8501 \
  -e AWS_DEFAULT_REGION=us-east-2 \
  -e AWS_REGION=us-east-2 \
  -e BIXI_RUN_ID=cloud-2024 \
  -e BIXI_PIPELINE_BUCKET=bixistorage-pipelinebucketb967bd35-icnkid23rfsa \
  -e BIXI_PIPELINE_PREFIX=bixi-mlops \
  -e BIXI_DATA_BUCKET=insy684 \
  -e BIXI_BASELINE_PREFIX=bixi-serving-artifacts \
  bixi-streamlit-ec2
```

Then open:

```text
http://<EC2-public-ip>:8501
```

## Useful Commands

View logs:

```bash
docker logs -f bixi-streamlit-ec2
```

Restart:

```bash
docker restart bixi-streamlit-ec2
```

Stop:

```bash
docker stop bixi-streamlit-ec2
```

Remove:

```bash
docker rm -f bixi-streamlit-ec2
```

## Verification Checklist

- The EC2 instance has an IAM role attached.
- The IAM role can read the required S3 prefixes.
- Security group allows inbound `8501`.
- `docker logs` shows Streamlit running without S3 permission errors.
- Page 1 predictions work.
- Page 2 custom weather predictions work.
- Page 3 monitoring artifacts load.
