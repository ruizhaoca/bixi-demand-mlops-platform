"""Raw BIXI trip ingestion + 15-minute demand cleaning.

This module turns the official BIXI open-data trip archives into the cleaned,
15-minute station-level demand tables that the feature-engineering stage consumes:

    s3://<DATA_BUCKET>/<DATA_PREFIX>/{2024,2025_may,2025_oct}_{departure,arrival}_demand_15min.csv
        columns: station_name, time_15min, latitude, longitude, demand

It is **importable and idempotent**: ``download_raw_trips`` skips years already in
S3, and ``process_year`` skips periods whose output CSVs already exist (unless
``force=True``). It uses the shared :mod:`bixi.config` / :mod:`bixi.io` helpers
(default boto3 credential chain) and the stdlib (``urllib.request`` + ``zipfile``)
so it needs no extra runtime dependencies beyond the training image.

Wired into the pipeline via :func:`bixi.ingest.ensure_raw_in_s3` (the ``ingest``
stage); also runnable standalone with ``python -m bixi.demand_ingestion_cleaning``.
"""

from __future__ import annotations

import io as _io
import urllib.request
import zipfile

import pandas as pd

from . import config, io

MONTREAL_TZ = "America/Montreal"
MAX_TRIP_DURATION = pd.Timedelta(minutes=180)
_DOWNLOAD_TIMEOUT = 600

# Canonical BIXI open-data trip archives (full-year zips, one CSV member each).
TRIP_ZIP_URLS = {
    "2024": "https://s3.ca-central-1.amazonaws.com/cdn.bixi.com/wp-content/uploads/2025/01/DonneesOuvertes2024_010203040506070809101112.zip",
    "2025": "https://s3.ca-central-1.amazonaws.com/cdn.bixi.com/wp-content/uploads/2026/02/DonneesOuvertes2025_010203040506070809101112.zip",
}

# Where each year's extracted trip CSV lands in S3 (member name == this basename).
TRIP_CSV_KEYS = {
    "2024": f"{config.RAW_PREFIX}/2024/DonneesOuvertes2024_010203040506070809101112.csv",
    "2025": f"{config.RAW_PREFIX}/2025/DonneesOuvertes2025_010203040506070809101112.csv",
}

# Output demand tables: (year_label, source year, source-zip key, months filter).
DEMAND_PERIODS = [
    ("2024", "2024", 2024, None),
    ("2025_may", "2025", 2025, [5]),
    ("2025_oct", "2025", 2025, [10]),
]

REQUIRED_TRIP_COLUMNS = {
    "STARTSTATIONNAME",
    "ENDSTATIONNAME",
    "STARTTIMEMS",
    "ENDTIMEMS",
    "STARTSTATIONLATITUDE",
    "STARTSTATIONLONGITUDE",
    "ENDSTATIONLATITUDE",
    "ENDSTATIONLONGITUDE",
}


def log(message: str) -> None:
    print(message, flush=True)


# --------------------------------------------------------------------------- #
# 1. Download + extract raw trip archives into S3 (idempotent)
# --------------------------------------------------------------------------- #
def _prefix_has_objects(prefix: str) -> bool:
    r = io.s3().list_objects_v2(Bucket=config.DATA_BUCKET, Prefix=prefix, MaxKeys=1)
    return r.get("KeyCount", 0) > 0


def download_raw_trips(force: bool = False) -> list[str]:
    """Download each canonical trip zip and extract its members to S3.

    Members land under ``s3://<DATA_BUCKET>/<RAW_PREFIX>/<year>/<member>``.
    Idempotent: a year whose prefix already holds objects is skipped unless
    ``force``.
    """
    uploaded: list[str] = []
    for year, url in TRIP_ZIP_URLS.items():
        prefix = f"{config.RAW_PREFIX}/{year}/"
        if _prefix_has_objects(prefix) and not force:
            log(f"[ingest] raw trips for {year} already in S3 — skip download.")
            continue
        log(f"[ingest] downloading {year} trip archive...")
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as resp:
            content = resp.read()
        with zipfile.ZipFile(_io.BytesIO(content)) as z:
            for member in z.namelist():
                if member.endswith("/"):
                    continue
                key = f"{prefix}{member}"
                io.put_bytes(key, z.read(member), bucket=config.DATA_BUCKET)
                uploaded.append(key)
                log(f"[ingest]   extracted -> s3://{config.DATA_BUCKET}/{key}")
    return uploaded


# --------------------------------------------------------------------------- #
# 2. Clean + aggregate one period to 15-minute demand (idempotent)
# --------------------------------------------------------------------------- #
def validate_trip_columns(df: pd.DataFrame) -> None:
    missing_cols = REQUIRED_TRIP_COLUMNS - set(df.columns)
    if missing_cols:
        missing = ", ".join(sorted(missing_cols))
        raise ValueError(f"Trip data is missing required columns: {missing}")


def prepare_trip_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse millisecond timestamps as UTC, convert to Montreal local time, and
    drop the timezone for downstream joins/aggregation."""
    start_utc = pd.to_datetime(df["STARTTIMEMS"], unit="ms", utc=True, errors="coerce")
    end_utc = pd.to_datetime(df["ENDTIMEMS"], unit="ms", utc=True, errors="coerce")

    df = df.copy()
    df["STARTTIMEMS"] = start_utc.dt.tz_convert(MONTREAL_TZ).dt.tz_localize(None)
    df["ENDTIMEMS"] = end_utc.dt.tz_convert(MONTREAL_TZ).dt.tz_localize(None)
    df["_duration"] = end_utc - start_utc

    return df


def filter_valid_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Keep trips with complete stations/timestamps and a valid duration."""
    df = df.copy()
    station_cols = ["STARTSTATIONNAME", "ENDSTATIONNAME"]
    df[station_cols] = df[station_cols].replace(r"^\s*$", pd.NA, regex=True)

    mask = (
        df["STARTSTATIONNAME"].notna()
        & df["ENDSTATIONNAME"].notna()
        & df["STARTTIMEMS"].notna()
        & df["ENDTIMEMS"].notna()
        & df["_duration"].gt(pd.Timedelta(0))
        & df["_duration"].le(MAX_TRIP_DURATION)
    )
    filtered = df.loc[mask].drop(columns=["_duration"]).copy()
    log(f"  Valid trip filter: kept {len(filtered):,} of {len(df):,} rows")
    return filtered


def filter_event_year(subset: pd.DataFrame, expected_year: int | None, trip_type: str) -> pd.DataFrame:
    """Keep only events whose local timestamp belongs to ``expected_year``.

    Departures key on STARTTIMEMS and arrivals on ENDTIMEMS, so each demand table
    is filtered by its own event time.
    """
    if expected_year is None:
        return subset
    mask = subset["datetime"].dt.year.eq(expected_year)
    filtered = subset.loc[mask].copy()
    log(f"  {trip_type} year filter {expected_year}: "
        f"kept {len(filtered):,} of {len(subset):,} rows")
    return filtered


def _demand_output_key(year_label: str, trip_type: str) -> str:
    return f"{config.DATA_PREFIX}/{year_label}_{trip_type}_demand_15min.csv"


def process_year(s3_key: str, year_label: str, expected_year: int | None = None,
                 months: list[int] | None = None, force: bool = False) -> list[str]:
    """Build the 15-minute departure + arrival demand CSVs for one period.

    Reads the cleaned trip CSV from ``s3_key``, removes invalid trips, splits into
    departures/arrivals, filters by local (year, months), floors to 15 minutes and
    counts events per station/slot. Idempotent: skips when **both** output CSVs
    already exist unless ``force``.
    """
    out_keys = {t: _demand_output_key(year_label, t) for t in ("departure", "arrival")}
    if not force and all(io.exists(k, bucket=config.DATA_BUCKET) for k in out_keys.values()):
        log(f"[ingest] demand tables for {year_label} already in S3 — skip.")
        return []

    log(f"\nLoading s3://{config.DATA_BUCKET}/{s3_key} ...")
    df = pd.read_csv(_io.BytesIO(io.get_bytes(s3_key, bucket=config.DATA_BUCKET)))

    validate_trip_columns(df)
    df = prepare_trip_timestamps(df)
    df = filter_valid_trips(df)

    written: list[str] = []
    for trip_type in ("departure", "arrival"):
        if trip_type == "departure":
            cols = ["STARTSTATIONNAME", "STARTTIMEMS",
                    "STARTSTATIONLATITUDE", "STARTSTATIONLONGITUDE"]
        else:
            cols = ["ENDSTATIONNAME", "ENDTIMEMS",
                    "ENDSTATIONLATITUDE", "ENDSTATIONLONGITUDE"]
        subset = df[cols].copy()
        subset.columns = ["station_name", "datetime", "latitude", "longitude"]

        subset = filter_event_year(subset, expected_year, trip_type)
        if months:
            subset = subset[subset["datetime"].dt.month.isin(months)]

        subset["time_15min"] = subset["datetime"].dt.floor("15min")
        demand = (
            subset.groupby(["station_name", "time_15min", "latitude", "longitude"])
            .size()
            .reset_index(name="demand")
        )

        out_key = out_keys[trip_type]
        buf = _io.StringIO()
        demand.to_csv(buf, index=False)
        io.put_bytes(out_key, buf.getvalue().encode(), bucket=config.DATA_BUCKET,
                     content_type="text/csv")
        written.append(out_key)
        log(f"  Uploaded: s3://{config.DATA_BUCKET}/{out_key}, shape: {demand.shape}")
    return written


def build_demand_tables(force: bool = False) -> list[str]:
    """Build all three periods (2024 full year, 2025 May, 2025 Oct) for both targets.

    Assumes the raw trip CSVs already exist in S3 (call :func:`download_raw_trips`
    first; the ingest stage does both in order).
    """
    written: list[str] = []
    for year_label, src_year, expected_year, months in DEMAND_PERIODS:
        written += process_year(
            s3_key=TRIP_CSV_KEYS[src_year],
            year_label=year_label,
            expected_year=expected_year,
            months=months,
            force=force,
        )
    return written


def main(force: bool = False) -> None:
    download_raw_trips(force=force)
    build_demand_tables(force=force)
    log("\nDemand ingestion + cleaning complete.")


if __name__ == "__main__":
    main()
