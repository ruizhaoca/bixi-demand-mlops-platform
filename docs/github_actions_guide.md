# GitHub Actions CI Guide

This project uses GitHub Actions to check that the code tests and the container
images build before changes are merged into `main`.

## What The CI Workflow Does

The workflow is defined in:

```text
.github/workflows/ci.yml
```

The single `test-and-build` job runs these steps:

1. Install dependencies from `requirements.txt` (Streamlit serving) and
   `requirements-train.txt` (pipeline / training), plus `pytest`.
2. Run the test suite: `pytest -q tests/`.
3. Build the training / pipeline image: `docker build -f docker/Dockerfile.train -t bixi-pipeline .`.
4. Build the EC2 Streamlit image: `docker build -f docker/Dockerfile.streamlit_ec2 -t bixi-streamlit .`.
5. Smoke-test the pipeline image with no AWS: `docker run --rm bixi-pipeline --help`.

If every step passes, the pull request gets a green check. If any step fails,
GitHub shows a red X and the branch should be fixed before merging.

## When It Runs

The workflow runs automatically when:

- A pull request is opened or updated against `main`.
- Code is pushed to `main` (or the legacy `Louis'-modification` branches).

It can also be run manually from the GitHub website:

```text
Repository -> Actions -> CI -> Run workflow
```

## How This Fits The Team Git Workflow

Recommended process:

1. Create or switch to a feature branch.
2. Make local changes.
3. Commit and push the feature branch.
4. Open a pull request into `main`.
5. Wait for the CI check to finish.
6. Ask a teammate to review the pull request (you cannot approve your own).
7. Merge only after CI is green and the review is complete.

This protects `main` from broken tests, missing dependencies, or Docker build errors.

## What To Do If CI Fails

Open the failed workflow run and check which step failed:

- `Install dependencies`: usually a missing or incompatible package in
  `requirements.txt` / `requirements-train.txt`.
- `Run tests`: a Python code or test-behavior issue.
- `Build ... image`: a Dockerfile, dependency, or missing-file issue.
- `Smoke test pipeline image`: a runtime dependency or `bixi.pipeline` import issue.

Fix the issue locally, run the same command locally, commit the fix, and push
again. GitHub Actions reruns automatically.

## Local Commands That Match CI

```bash
# Tests (scope to tests/ so stale infra/cdk.out copies aren't collected)
pytest -q tests/

# Build both images
docker build -f docker/Dockerfile.train -t bixi-pipeline .
docker build -f docker/Dockerfile.streamlit_ec2 -t bixi-streamlit .

# Smoke-test the pipeline image (no AWS needed)
docker run --rm bixi-pipeline --help
```

## Current Deployment Boundary

CI verifies that the code can be tested and that both images build and start.
It does **not** deploy to AWS. The Streamlit Community Cloud app auto-deploys
from `main` on its own; the EC2 image is rebuilt and redeployed manually (see
[`ec2_streamlit_deployment_guide.md`](ec2_streamlit_deployment_guide.md)), and
the training pipeline runs on AWS Batch via the CDK infra (see the README).
