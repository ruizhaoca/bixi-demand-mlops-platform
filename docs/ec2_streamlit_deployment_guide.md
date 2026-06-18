# EC2-Only Streamlit Deployment Guide

This deployment option runs Streamlit directly on an EC2 instance and loads
Phase-2 model artifacts from S3 at runtime.

It is separate from the Streamlit Community Cloud deployment:

- Community Cloud entrypoint: `app.py`
- EC2 entrypoint: `app_ec2.py`

The EC2 version is S3-first and does not use the packaged local artifacts under
`artifacts/streamlit-community-cloud/`.

## Current Demo Deployment

For the current presentation demo, the EC2 deployment is:

```text
Instance name: bixi
Instance ID: i-0c59b48363403e312
Recommended instance type: t3.medium
Elastic IP: 3.16.250.166
Public app URL: http://3.16.250.166:8501
IAM role: bixi-ec2-s3-read-role
Container name: bixi-streamlit-ec2
```

The EC2 terminal page does not need to stay open. The Streamlit app runs inside a
detached Docker container. The app stays available as long as the EC2 instance is
running, the container is running, and the security group allows inbound `8501`.

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

For the current demo, the existing role `bixi-ec2-s3-read-role` can be used
because its trusted entity is EC2 and it has S3 access. Attach it from:

```text
EC2 -> Instances -> select bixi
Actions -> Security -> Modify IAM role
```

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

For the current demo, the Elastic IP is:

```text
http://3.16.250.166:8501
```

If others need to open the app, make sure the `8501` inbound source is
`0.0.0.0/0`. If the source is `My IP`, only your current network can open it.

## Elastic IP And Instance Size

The app is more stable on `t3.medium` than `t3.micro`, especially for the full-day
Plotly chart on Page 1 Tab 2.

If you need to change the instance type:

```text
EC2 -> Instances -> select bixi
Instance state -> Stop instance
Actions -> Instance settings -> Change instance type -> t3.medium
Instance state -> Start instance
```

Keep the Elastic IP associated with the instance before stopping it. That keeps
the public URL stable after restart.

To create a stable URL:

```text
EC2 -> Elastic IPs -> Allocate Elastic IP address
Public IPv4 address pool: Amazon's pool of IPv4 addresses
Actions -> Associate Elastic IP address
Resource type: Instance
Instance: bixi / i-0c59b48363403e312
Private IP address: leave blank unless AWS requires a value
```

Elastic IP and public IPv4 addresses can create AWS charges. Release the Elastic
IP after the presentation if the fixed URL is no longer needed.

## Connect To EC2

The easiest option is AWS Console EC2 Instance Connect:

```text
EC2 -> Instances -> select bixi -> Connect
Connection type: Connect using a Public IP
Username: ubuntu
```

This replaces the local laptop SSH command and does not require a `.pem` file.

If you do have the key pair, local SSH also works:

```bash
ssh -i /path/to/key.pem ubuntu@3.16.250.166
```

## Install Docker On EC2

Run this once on the EC2 terminal:

```bash
sudo apt update
sudo apt install -y docker.io git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu
```

Then disconnect and reconnect to EC2 so the `docker` group permission takes
effect. Confirm Docker works:

```bash
docker ps
```

## Build And Run On EC2

After this EC2 work is merged, deploy from `main`:

```bash
git clone https://github.com/ruizhaoca/bixi-demand-mlops-platform.git
cd bixi-demand-mlops-platform
git checkout main
```

If you are testing before merge, checkout the active EC2 feature branch instead.

If the repo already exists on the EC2 instance, update it instead of cloning:

```bash
cd ~/bixi-demand-mlops-platform
git fetch origin
git checkout main
git pull origin main
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
http://3.16.250.166:8501
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

If the old FastAPI container is still running on port `8000`, it does not
conflict with Streamlit on `8501`. If memory is tight, it can be stopped:

```bash
docker stop bixi-demand-api
docker restart bixi-streamlit-ec2
```

## Browser Notes

When Streamlit prints URLs, use the external URL from your laptop or from a
teammate's computer:

```text
External URL: http://3.16.250.166:8501
```

Do not use these from your laptop browser:

```text
Local URL: http://localhost:8501
Network URL: http://172.17.x.x:8501
```

Those addresses only make sense inside the EC2/container network.

If the Page 1 full-day Plotly chart shows a dynamic import error, try:

```text
Ctrl + Shift + R
```

or open the app in an incognito/private browser window. This is usually a
browser-side Streamlit static-file cache issue.

## Verification Checklist

- The EC2 instance has an IAM role attached.
- The IAM role can read the required S3 prefixes.
- Security group allows inbound `8501`.
- The app URL is `http://3.16.250.166:8501`.
- `docker logs` shows Streamlit running without S3 permission errors.
- Page 1 predictions work.
- Page 2 custom weather predictions work.
- Page 3 monitoring artifacts load.
