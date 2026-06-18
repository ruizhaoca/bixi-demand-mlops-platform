"""Download packaged local artifacts for Streamlit Community Cloud fallback.

This script is read-only against the model/pipeline S3 locations. It downloads
the minimal serving bundle needed for the Streamlit app to run without AWS
resources after teardown:

* Phase-2 model checkpoints and encoders from the CDK pipeline bucket.
* Compact 2026 serving baselines from the persistent ``insy684`` bucket.
* Small JSON/CSV metadata for the monitoring page.

Presentation images already committed under ``docs/presentation`` are not
downloaded again.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bixi import config  # noqa: E402


DEFAULT_PIPELINE_BUCKET = "bixistorage-pipelinebucketb967bd35-icnkid23rfsa"
DEFAULT_DATA_BUCKET = "insy684"
DEFAULT_PIPELINE_PREFIX = "bixi-mlops"
DEFAULT_BASELINE_PREFIX = "bixi-serving-artifacts"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "streamlit-community-cloud"
PREFERRED_RUN_IDS = ("cloud-2024", "2024-prod", "cloud")


@dataclass(frozen=True)
class ArtifactSpec:
    bucket: str
    key: str
    local_path: Path
    required: bool = True
    source: str = "pipeline"


def load_env_file(path: Path | None) -> None:
    """Load simple KEY=VALUE pairs without printing secrets."""
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def s3_object_info(s3_client, bucket: str, key: str) -> dict | None:
    try:
        return s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def list_run_ids(s3_client, bucket: str, pipeline_prefix: str) -> list[str]:
    prefix = f"{pipeline_prefix.rstrip('/')}/runs/"
    paginator = s3_client.get_paginator("list_objects_v2")
    run_ids: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for item in page.get("CommonPrefixes", []):
            name = item["Prefix"][len(prefix):].strip("/")
            if name:
                run_ids.append(name)
    return sorted(set(run_ids))


def has_required_bundle(
    s3_client,
    run_id: str,
    pipeline_bucket: str,
    pipeline_prefix: str,
    data_bucket: str,
    baseline_prefix: str,
) -> bool:
    for target in config.TARGETS:
        required_keys = [
            (pipeline_bucket, f"{pipeline_prefix}/runs/{run_id}/{target}/train/best_model.pkl"),
            (pipeline_bucket, f"{pipeline_prefix}/runs/{run_id}/{target}/data/encoder.pkl"),
            (data_bucket, f"{baseline_prefix}/{run_id}/{target}/serving_baselines.parquet"),
        ]
        for bucket, key in required_keys:
            if s3_object_info(s3_client, bucket, key) is None:
                return False
    return True


def resolve_run_id(
    s3_client,
    requested: str,
    pipeline_bucket: str,
    pipeline_prefix: str,
    data_bucket: str,
    baseline_prefix: str,
) -> str:
    if requested != "auto":
        return requested

    discovered = list_run_ids(s3_client, pipeline_bucket, pipeline_prefix)
    candidates = list(dict.fromkeys([*PREFERRED_RUN_IDS, *discovered]))
    for run_id in candidates:
        if has_required_bundle(
            s3_client=s3_client,
            run_id=run_id,
            pipeline_bucket=pipeline_bucket,
            pipeline_prefix=pipeline_prefix,
            data_bucket=data_bucket,
            baseline_prefix=baseline_prefix,
        ):
            print(f"Resolved run id: {run_id}", flush=True)
            return run_id

    raise RuntimeError(
        "Could not find a run id with model, encoder, and serving baseline artifacts. "
        f"Discovered pipeline run ids: {discovered}"
    )


def artifact_specs(
    run_id: str,
    pipeline_bucket: str,
    pipeline_prefix: str,
    data_bucket: str,
    baseline_prefix: str,
    output_root: Path,
) -> list[ArtifactSpec]:
    specs: list[ArtifactSpec] = []
    bundle_root = output_root / run_id
    for target in config.TARGETS:
        target_root = bundle_root / target
        run_prefix = f"{pipeline_prefix.rstrip('/')}/runs/{run_id}/{target}"
        specs.extend(
            [
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/train/best_model.pkl",
                    target_root / "train" / "best_model.pkl",
                    source="pipeline-model",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/data/encoder.pkl",
                    target_root / "data" / "encoder.pkl",
                    source="pipeline-encoder",
                ),
                ArtifactSpec(
                    data_bucket,
                    f"{baseline_prefix.rstrip('/')}/{run_id}/{target}/serving_baselines.parquet",
                    target_root / "data" / "serving_baselines.parquet",
                    source="serving-baseline",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/train/metrics.json",
                    target_root / "metadata" / "metrics.json",
                    source="pipeline-metadata",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/data/data_summary.json",
                    target_root / "metadata" / "data_summary.json",
                    source="pipeline-metadata",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/data/tiers.json",
                    target_root / "metadata" / "tiers.json",
                    required=False,
                    source="pipeline-metadata",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/fairness/fairness_report.json",
                    target_root / "monitoring" / "fairness_report.json",
                    required=False,
                    source="pipeline-monitoring",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/drift/drift_summary.json",
                    target_root / "monitoring" / "drift_summary.json",
                    required=False,
                    source="pipeline-monitoring",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/register/registered_model.json",
                    target_root / "metadata" / "registered_model.json",
                    required=False,
                    source="pipeline-metadata",
                ),
                ArtifactSpec(
                    pipeline_bucket,
                    f"{run_prefix}/explain/shap_importance.csv",
                    target_root / "monitoring" / "shap_importance.csv",
                    required=False,
                    source="pipeline-monitoring",
                ),
            ]
        )
    return specs


def download_artifact(s3_client, spec: ArtifactSpec, overwrite: bool) -> dict:
    info = s3_object_info(s3_client, spec.bucket, spec.key)
    if info is None:
        if spec.required:
            raise FileNotFoundError(f"Required S3 object not found: s3://{spec.bucket}/{spec.key}")
        return {
            "status": "missing_optional",
            "bucket": spec.bucket,
            "key": spec.key,
            "local_path": str(spec.local_path.relative_to(REPO_ROOT)),
            "required": spec.required,
            "source": spec.source,
        }

    remote_size = int(info["ContentLength"])
    if spec.local_path.exists() and not overwrite and spec.local_path.stat().st_size == remote_size:
        status = "skipped_existing"
    else:
        spec.local_path.parent.mkdir(parents=True, exist_ok=True)
        s3_client.download_file(spec.bucket, spec.key, str(spec.local_path))
        status = "downloaded"

    return {
        "status": status,
        "bucket": spec.bucket,
        "key": spec.key,
        "local_path": str(spec.local_path.relative_to(REPO_ROOT)),
        "required": spec.required,
        "source": spec.source,
        "bytes": remote_size,
        "last_modified": info["LastModified"].isoformat(),
        "etag": info.get("ETag", "").strip('"'),
    }


def write_manifest(output_root: Path, run_id: str, records: list[dict]) -> Path:
    manifest_path = output_root / run_id / "artifact_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "deployment_option": "streamlit-community-cloud-packaged-local-artifacts",
        "run_id": run_id,
        "note": "Presentation images are intentionally reused from docs/presentation and not duplicated here.",
        "artifacts": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download packaged Streamlit local fallback artifacts.")
    parser.add_argument("--run-id", default="auto", help="cloud-2024, 2024-prod, cloud, or auto")
    parser.add_argument("--pipeline-bucket", default=DEFAULT_PIPELINE_BUCKET)
    parser.add_argument("--pipeline-prefix", default=DEFAULT_PIPELINE_PREFIX)
    parser.add_argument("--data-bucket", default=DEFAULT_DATA_BUCKET)
    parser.add_argument("--baseline-prefix", default=DEFAULT_BASELINE_PREFIX)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", config.AWS_REGION))
    parser.add_argument("--env-file", default=str(REPO_ROOT.parent / ".env"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file) if args.env_file else None)

    s3_client = boto3.client("s3", region_name=args.region)
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (REPO_ROOT / output_root).resolve()

    run_id = resolve_run_id(
        s3_client=s3_client,
        requested=args.run_id,
        pipeline_bucket=args.pipeline_bucket,
        pipeline_prefix=args.pipeline_prefix.rstrip("/"),
        data_bucket=args.data_bucket,
        baseline_prefix=args.baseline_prefix.rstrip("/"),
    )

    specs = artifact_specs(
        run_id=run_id,
        pipeline_bucket=args.pipeline_bucket,
        pipeline_prefix=args.pipeline_prefix.rstrip("/"),
        data_bucket=args.data_bucket,
        baseline_prefix=args.baseline_prefix.rstrip("/"),
        output_root=output_root,
    )
    records = [download_artifact(s3_client, spec, overwrite=args.overwrite) for spec in specs]
    manifest_path = write_manifest(output_root, run_id, records)

    for record in records:
        suffix = f" ({record.get('bytes', 0):,} bytes)" if "bytes" in record else ""
        print(f"{record['status']}: {record['local_path']}{suffix}", flush=True)
    print(f"manifest: {manifest_path.relative_to(REPO_ROOT)}", flush=True)


if __name__ == "__main__":
    main()
