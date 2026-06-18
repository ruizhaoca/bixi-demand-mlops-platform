import io
import os
import zipfile

import boto3
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client("s3")
BUCKET = os.getenv("S3_BUCKET", "insy684")
MONTREAL_TZ = "America/Montreal"
MAX_TRIP_DURATION = pd.Timedelta(minutes=180)

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


# 1. Download and upload raw BIXI trip data.

urls = {
    "2024": "https://s3.ca-central-1.amazonaws.com/cdn.bixi.com/wp-content/uploads/2025/01/DonneesOuvertes2024_010203040506070809101112.zip",
    "2025": "https://s3.ca-central-1.amazonaws.com/cdn.bixi.com/wp-content/uploads/2026/02/DonneesOuvertes2025_010203040506070809101112.zip",
}

for year, url in urls.items():
    print(f"Downloading {year} trip data...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        for filename in z.namelist():
            if filename.endswith("/"):
                continue

            with z.open(filename) as f:
                s3_key = f"bixi-data/{year}/{filename}"
                s3.upload_fileobj(f, BUCKET, s3_key)
                print(f"  Uploaded: {s3_key}")


# 2. Split and aggregate demand at 15-minute level.

def validate_trip_columns(df):
    missing_cols = REQUIRED_TRIP_COLUMNS - set(df.columns)
    if missing_cols:
        missing = ", ".join(sorted(missing_cols))
        raise ValueError(f"Trip data is missing required columns: {missing}")


def prepare_trip_timestamps(df):
    """
    Parse raw millisecond timestamps as UTC, convert them to Montreal local time,
    and remove timezone information for downstream joins and aggregation.
    """
    start_utc = pd.to_datetime(df["STARTTIMEMS"], unit="ms", utc=True, errors="coerce")
    end_utc = pd.to_datetime(df["ENDTIMEMS"], unit="ms", utc=True, errors="coerce")

    df = df.copy()
    df["STARTTIMEMS"] = start_utc.dt.tz_convert(MONTREAL_TZ).dt.tz_localize(None)
    df["ENDTIMEMS"] = end_utc.dt.tz_convert(MONTREAL_TZ).dt.tz_localize(None)
    df["_duration"] = end_utc - start_utc

    return df


def filter_event_year(subset, expected_year, trip_type):
    """
    Keep only events whose local event timestamp belongs to the requested year.

    Departures use STARTTIMEMS, and arrivals use ENDTIMEMS because each demand
    table is keyed by its own event time.
    """
    if expected_year is None:
        return subset

    mask = subset["datetime"].dt.year.eq(expected_year)
    filtered = subset.loc[mask].copy()
    print(
        f"  {trip_type} year filter {expected_year}: "
        f"kept {len(filtered):,} of {len(subset):,} rows"
    )

    return filtered


def filter_valid_trips(df):
    """
    Keep trips with complete stations/timestamps and a valid duration.
    """
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
    print(f"  Valid trip filter: kept {len(filtered):,} of {len(df):,} rows")

    return filtered


def process_year(s3_key, year_label, expected_year=None, months=None):
    """
    Load trip data from S3, clean invalid trips, split into departures and
    arrivals, optionally filter by local month, aggregate at 15-minute level,
    and upload the result.
    """
    print(f"\nLoading {s3_key}...")
    obj = s3.get_object(Bucket=BUCKET, Key=s3_key)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))

    validate_trip_columns(df)
    df = prepare_trip_timestamps(df)
    df = filter_valid_trips(df)

    for trip_type in ["departure", "arrival"]:
        if trip_type == "departure":
            subset = df[[
                "STARTSTATIONNAME",
                "STARTTIMEMS",
                "STARTSTATIONLATITUDE",
                "STARTSTATIONLONGITUDE",
            ]].copy()
            subset.columns = ["station_name", "datetime", "latitude", "longitude"]
        else:
            subset = df[[
                "ENDSTATIONNAME",
                "ENDTIMEMS",
                "ENDSTATIONLATITUDE",
                "ENDSTATIONLONGITUDE",
            ]].copy()
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

        out_key = f"processed-data/{year_label}_{trip_type}_demand_15min.csv"
        buf = io.StringIO()
        demand.to_csv(buf, index=False)
        s3.put_object(Bucket=BUCKET, Key=out_key, Body=buf.getvalue())
        print(f"  Uploaded: {out_key}, shape: {demand.shape}")


# 2024 full year
process_year(
    s3_key="bixi-data/2024/DonneesOuvertes2024_010203040506070809101112.csv",
    year_label="2024",
    expected_year=2024,
)

# 2025 May validation and October test sets
process_year(
    s3_key="bixi-data/2025/DonneesOuvertes2025_010203040506070809101112.csv",
    year_label="2025_may",
    expected_year=2025,
    months=[5],
)
process_year(
    s3_key="bixi-data/2025/DonneesOuvertes2025_010203040506070809101112.csv",
    year_label="2025_oct",
    expected_year=2025,
    months=[10],
)

print("\nAll done!")
