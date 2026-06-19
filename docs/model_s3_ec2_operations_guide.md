# Model / S3 / EC2 Operations Guide (Superseded)

> **This document is superseded.** It originally described an early **FastAPI**
> backend (port 8000, `/predict` `/health` `/docs`) that loaded a course-1-era
> *hourly*, 400-station LightGBM model from `s3://insy684/bixi-models/`. That
> backend was **removed** when the project moved to serving everything through
> **Streamlit** (`api/`, `src/predictor.py`, `src/s3_io.py`, and `tests/test_api.py`
> were deleted). The current platform predicts **15-minute** demand for all
> ~1,100+ stations, separately for departures and arrivals, and there is no
> FastAPI service. The old commands, EC2 IP, model schema, and S3 paths in the
> prior version of this file no longer apply — see the git history if you need them.

## Where the current operations are documented

| Topic | Doc |
|---|---|
| EC2 Streamlit deployment (build, run, redeploy on port 8501) | [`ec2_streamlit_deployment_guide.md`](ec2_streamlit_deployment_guide.md) |
| Pipeline, MLflow, S3 layout, AWS CDK infra | [`phase2_modeling.md`](phase2_modeling.md) |
| Where every asset lives in S3 + MLflow | [`../README.md`](../README.md) — “Where every asset lives” |
| Net-flow rebalancing layer | [`phase3_rebalancing.md`](phase3_rebalancing.md) |
| CI (tests + image builds) | [`github_actions_guide.md`](github_actions_guide.md) |

## Operating principles that still hold

These team rules from the original guide remain valid regardless of serving tech:

- **S3 is the shared source of truth** for raw data, processed data, feature
  tables, and model artifacts — not GitHub, and not the EC2 disk. Keep raw data
  immutable; write transformed data to new, versioned prefixes.
- **No static AWS keys anywhere.** Code uses the default boto3 credential chain:
  SSO locally, an attached **IAM role** on EC2 / AWS Batch. Never commit `.env`,
  `*.pem`, or access keys; rotate any key that leaks.
- **Match code to the model schema.** If the feature contract changes, update the
  serving/feature code and the committed artifacts together — do not ship a model
  whose schema the serving layer does not expect.
