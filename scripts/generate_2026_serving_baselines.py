"""Manually generate the serving baseline stage.

The normal cloud pipeline now performs this work automatically. This wrapper is
retained for targeted repairs and local operations.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from bixi import config  # noqa: E402
from bixi.serving_baselines import build_serving_baselines, generate_for_target  # noqa: E402,F401


def load_env_file(path: Path | None) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate S3 serving baselines.")
    parser.add_argument("--run-id", default=os.getenv("BIXI_RUN_ID", "cloud-2024"))
    parser.add_argument("--source-bucket")
    parser.add_argument("--source-prefix")
    parser.add_argument("--output-bucket")
    parser.add_argument("--output-prefix")
    parser.add_argument("--targets", default="both", help="departure | arrival | both")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--env-file", default=str(REPO_ROOT.parent / ".env"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(Path(args.env_file) if args.env_file else None)
    targets = config.TARGETS if args.targets == "both" else (args.targets,)
    source_bucket = args.source_bucket or os.getenv("BIXI_DATA_BUCKET", config.DATA_BUCKET)
    output_bucket = args.output_bucket or os.getenv("BIXI_DATA_BUCKET", config.DATA_BUCKET)
    source_prefix = args.source_prefix or os.getenv("BIXI_DATA_PREFIX", config.DATA_PREFIX)
    output_prefix = args.output_prefix or os.getenv(
        "BIXI_SERVING_PREFIX", config.SERVING_PREFIX
    )

    for target in targets:
        uri = generate_for_target(
            target,
            args.run_id,
            source_bucket=source_bucket,
            source_prefix=source_prefix,
            output_bucket=output_bucket,
            output_prefix=output_prefix,
            force=args.force,
        )
        print(f"Wrote {uri}", flush=True)


if __name__ == "__main__":
    main()
