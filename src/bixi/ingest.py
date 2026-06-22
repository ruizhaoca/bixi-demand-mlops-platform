"""Raw-data ingestion stage: ensure the source BIXI trips + weather live in S3.

This makes the pipeline reproducible from scratch instead of assuming a manual
upload. It is **idempotent**: objects already in S3 are skipped.

  * Weather: pulled from the Open-Meteo archive API (stable, parameterised) and
    resampled to 15-minute resolution.
  * BIXI trips: downloaded from the official open-data URLs. Those URLs change per
    release, so they are configurable via ``BIXI_TRIP_URLS`` (JSON map of
    ``"<year>": "<zip-url>"``); see ``infra`` / README for the current links.
"""

from __future__ import annotations

import io as _io
import json
import os
import urllib.request

import pandas as pd

from . import config, io

MONTREAL_LAT, MONTREAL_LON = 45.5019, -73.5674
WEATHER_HOURLY = ("temperature_2m,precipitation,wind_speed_10m,"
                  "relative_humidity_2m,weather_code")

# Raw objects we expect to exist (matches the Phase-1 S3 layout).
EXPECTED_TRIPS = [f"{config.RAW_PREFIX}/{y}/" for y in (2024, 2025)]
EXPECTED_WEATHER = [
    f"{config.WEATHER_PREFIX}/2024_weather_15min.csv",
    f"{config.WEATHER_PREFIX}/2025-may_weather_15min.csv",
    f"{config.WEATHER_PREFIX}/2025-oct_weather_15min.csv",
]


def _prefix_has_objects(prefix: str) -> bool:
    r = io.s3().list_objects_v2(Bucket=config.DATA_BUCKET, Prefix=prefix, MaxKeys=1)
    return r.get("KeyCount", 0) > 0


def fetch_open_meteo_15min(start: str, end: str) -> pd.DataFrame:
    url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={MONTREAL_LAT}"
           f"&longitude={MONTREAL_LON}&start_date={start}&end_date={end}"
           f"&hourly={WEATHER_HOURLY}&timezone=America%2FToronto")
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    h = payload["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").resample("15min").ffill().reset_index()
    return df


def ensure_weather_in_s3(force: bool = False) -> list[str]:
    done = []
    periods = {"2024_weather_15min.csv": ("2024-01-01", "2024-12-31"),
               "2025-may_weather_15min.csv": ("2025-05-01", "2025-05-31"),
               "2025-oct_weather_15min.csv": ("2025-10-01", "2025-10-31")}
    for name, (start, end) in periods.items():
        key = f"{config.WEATHER_PREFIX}/{name}"
        if io.exists(key, bucket=config.DATA_BUCKET) and not force:
            continue
        df = fetch_open_meteo_15min(start, end)
        buf = _io.StringIO(); df.to_csv(buf, index=False)
        io.put_bytes(key, buf.getvalue().encode(), bucket=config.DATA_BUCKET,
                     content_type="text/csv")
        done.append(key)
    return done


def ensure_trips_in_s3(force: bool = False) -> list[str]:
    urls = json.loads(os.getenv("BIXI_TRIP_URLS", "{}"))
    done = []
    for year, url in urls.items():
        prefix = f"{config.RAW_PREFIX}/{year}/"
        if _prefix_has_objects(prefix) and not force:
            continue
        dest = f"{prefix}{os.path.basename(url)}"
        with urllib.request.urlopen(url, timeout=300) as resp:
            io.put_bytes(dest, resp.read(), bucket=config.DATA_BUCKET)
        done.append(dest)
    return done


def ensure_raw_in_s3(force: bool = False) -> dict:
    """Materialise every from-scratch input the feature stage needs in S3:

      (a) 15-minute Montreal weather (Open-Meteo),
      (b) the raw BIXI trip archives (downloaded + extracted), and
      (c) the cleaned 15-minute departure/arrival demand tables.

    Idempotent at every step — already-present objects are skipped unless
    ``force``. The cleaning logic lives in :mod:`bixi.demand_ingestion_cleaning`
    and is imported lazily so the heavy pandas-only path is not loaded by tests
    that merely import :mod:`bixi.ingest`.
    """
    have_trips = {p: _prefix_has_objects(p) for p in EXPECTED_TRIPS}
    have_weather = {k: io.exists(k, bucket=config.DATA_BUCKET) for k in EXPECTED_WEATHER}
    print(f"[ingest] trips present: {have_trips}")
    print(f"[ingest] weather present: {have_weather}")
    summary = {"have_trips": have_trips, "have_weather": have_weather}

    # (a) weather
    if not all(have_weather.values()) or force:
        summary["weather_ingested"] = ensure_weather_in_s3(force=force)

    # (b) raw trip archives: prefer the canonical extracted layout used by the
    # cleaning step; fall back to the BIXI_TRIP_URLS whole-zip upload if set.
    from . import demand_ingestion_cleaning as dic  # lazy: keep tests import-light

    summary["trips_extracted"] = dic.download_raw_trips(force=force)
    if os.getenv("BIXI_TRIP_URLS"):
        summary["trips_ingested"] = ensure_trips_in_s3(force=force)

    # (c) cleaned 15-minute demand tables (input to the feature stage)
    summary["demand_tables"] = dic.build_demand_tables(force=force)

    if (all(have_trips.values()) and all(have_weather.values())
            and not force and not summary.get("trips_extracted")
            and not summary.get("demand_tables")):
        print("[ingest] all raw inputs already present in S3 — nothing to do.")
    return summary
