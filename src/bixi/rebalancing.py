"""Net-flow rebalancing layer for the BIXI demand platform.

This module turns the two committed 15-minute demand models (``departure`` and
``arrival``) into an operational **rebalancing** tool. For a representative
weekday it predicts, per station and per 15-minute slot, the *net flow*

    net_flow(station, slot) = arrival_pred - departure_pred

(positive => the station is filling up / overflow risk; negative => the station
is draining / stockout risk). Cumulating net flow across the 96 daily slots gives
each station's relative occupancy trajectory, from which we read a **peak deficit**
(how many bikes the station runs short of its day-start level — stockout severity)
and a **peak surplus** (how much it overfills — dock-shortage severity). Stations
are ranked by the larger of the two into a rebalancing priority list, each tagged
with a direction: *needs bikes* or *needs docks*.

Honest limitation: the trip data carries no dock-capacity or real-time occupancy,
so the day starts from a common 0 reference. This yields a **relative** risk
ranking and priority order — not exact stockout clock-times or absolute fill levels.

Design split:
  * **Pure** (no models, no I/O, unit-testable): ``net_flow_frame``,
    ``station_risk``, ``rank_priorities``.
  * **Model-driven**: ``predict_netflow_day``, ``compute_rebalancing`` — predict
    off the committed serving bundles; ``main`` prints the top-20 priorities.

Run with no AWS::

    PYTHONPATH=src ./.venv/bin/python -m bixi.rebalancing
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from . import config
from . import streamlit_local_serving as serving

# A neutral weather vector for the representative day. Net flow is robust to the
# weather *level*: rain depresses departures and arrivals together, so it mostly
# cancels in arrival - departure. We therefore score rebalancing pressure under
# mild, dry conditions rather than chasing a specific forecast.
NEUTRAL_WEATHER: dict[str, float] = {
    "temperature_2m": 18.0,
    "precipitation": 0.0,
    "wind_speed_10m": 10.0,
    "relative_humidity_2m": 60.0,
    "weather_code": 1.0,
}

SLOTS_PER_DAY = 96

DEFAULT_CSV_PATH = (
    serving.DEFAULT_ARTIFACT_ROOT / "rebalancing" / "rebalancing_priorities.csv"
)

RISK_COLUMNS = [
    config.STATION_COL,
    "latitude",
    "longitude",
    "peak_deficit",
    "deficit_slot",
    "peak_surplus",
    "surplus_slot",
    "net_daily",
    "throughput",
    "risk_score",
    "direction",
]

NEEDS_BIKES = "needs bikes"
NEEDS_DOCKS = "needs docks"


# --------------------------------------------------------------------------- #
# Pure functions (model-free, unit-testable)
# --------------------------------------------------------------------------- #
def net_flow_frame(pred_df: pd.DataFrame) -> pd.DataFrame:
    """Add ``net_flow = arr_pred - dep_pred`` to a long prediction frame.

    Expects columns ``dep_pred`` and ``arr_pred``. Returns a copy; the input is
    left untouched.
    """
    out = pred_df.copy()
    out["net_flow"] = out["arr_pred"].astype(float) - out["dep_pred"].astype(float)
    return out


def station_risk(netflow_df: pd.DataFrame) -> pd.DataFrame:
    """Reduce per-slot net flow to one rebalancing-risk row per station.

    For each station, net flow is cumulated over the day (slots sorted ascending)
    to a relative occupancy trajectory starting from a 0 day-start reference.

    * ``peak_deficit`` = how far below the start level occupancy ever drops
      (= ``max(0, -min(cumulative))``) — bikes needed / stockout severity.
    * ``peak_surplus`` = how far above the start level it ever rises
      (= ``max(0, max(cumulative))``) — dock shortage / overflow severity.
    * ``deficit_slot`` / ``surplus_slot`` = the 15-min slot of the lowest /
      highest point of the trajectory.
    * ``net_daily`` = end-of-day cumulative net flow; ``throughput`` = total
      predicted dep + arr volume; ``risk_score`` = ``max(peak_deficit,
      peak_surplus)``; ``direction`` = ``"needs bikes"`` when the deficit
      dominates, else ``"needs docks"``.
    """
    ordered = netflow_df.sort_values([config.STATION_COL, "slot_of_day"])
    records = []
    for station, group in ordered.groupby(config.STATION_COL, sort=False):
        net = group["net_flow"].to_numpy(dtype="float64")
        slots = group["slot_of_day"].to_numpy()
        cumulative = np.cumsum(net)

        i_min = int(np.argmin(cumulative))
        i_max = int(np.argmax(cumulative))
        peak_deficit = float(max(0.0, -cumulative[i_min]))
        peak_surplus = float(max(0.0, cumulative[i_max]))

        throughput = float(
            group["dep_pred"].to_numpy(dtype="float64").sum()
            + group["arr_pred"].to_numpy(dtype="float64").sum()
        )
        records.append(
            {
                config.STATION_COL: station,
                "latitude": float(group["latitude"].iloc[0]),
                "longitude": float(group["longitude"].iloc[0]),
                "peak_deficit": peak_deficit,
                "deficit_slot": int(slots[i_min]),
                "peak_surplus": peak_surplus,
                "surplus_slot": int(slots[i_max]),
                "net_daily": float(cumulative[-1]),
                "throughput": throughput,
                "risk_score": max(peak_deficit, peak_surplus),
                "direction": NEEDS_BIKES if peak_deficit >= peak_surplus else NEEDS_DOCKS,
            }
        )
    return pd.DataFrame.from_records(records, columns=RISK_COLUMNS)


def rank_priorities(risk_df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """Sort stations by ``risk_score`` (desc) and add a 1-based ``priority`` rank.

    ``top_n`` truncates to the highest-priority stations when provided.
    """
    ranked = risk_df.sort_values(
        "risk_score", ascending=False, kind="mergesort"
    ).reset_index(drop=True)
    ranked.insert(0, "priority", np.arange(1, len(ranked) + 1))
    if top_n is not None:
        ranked = ranked.head(top_n).reset_index(drop=True)
    return ranked


# --------------------------------------------------------------------------- #
# Model-driven (predict off the committed serving bundles)
# --------------------------------------------------------------------------- #
def _predict_target(
    bundle: "serving.LocalTargetBundle",
    dayofweek: int,
    month: int,
    weather: Mapping[str, float],
    stations: list[str] | None,
) -> pd.DataFrame:
    """Predict one target's demand across the 96 slots of a representative day."""
    base = bundle.baselines[bundle.baselines["dayofweek"] == dayofweek].copy()
    if stations is not None:
        base = base[base[config.STATION_COL].isin(stations)]
    base["month"] = month
    for col, value in weather.items():
        base[col] = value

    encoded = bundle.encoder.transform(base)
    features = encoded[config.MODEL_FEATURES].astype("float32")
    pred = np.clip(bundle.model.predict(features), 0.0, None)

    return pd.DataFrame(
        {
            config.STATION_COL: base[config.STATION_COL].to_numpy(),
            "slot_of_day": base["slot_of_day"].to_numpy(),
            "latitude": base["latitude"].to_numpy(dtype="float64"),
            "longitude": base["longitude"].to_numpy(dtype="float64"),
            "pred": np.asarray(pred, dtype="float64"),
        }
    )


def predict_netflow_day(
    bundles: Mapping[str, "serving.LocalTargetBundle"],
    dayofweek: int = 1,
    month: int = 6,
    weather: Mapping[str, float] = NEUTRAL_WEATHER,
    stations: list[str] | None = None,
) -> pd.DataFrame:
    """Predict departure and arrival demand for every common station on one day.

    Returns a long frame: ``station_name, slot_of_day, latitude, longitude,
    dep_pred, arr_pred`` — restricted to stations served by *both* bundles.
    ``dayofweek`` follows pandas convention (0=Mon ... 6=Sun); default 1 = Tuesday.
    """
    if stations is None:
        stations = serving.common_stations(bundles)

    departure = _predict_target(bundles["departure"], dayofweek, month, weather, stations)
    arrival = _predict_target(bundles["arrival"], dayofweek, month, weather, stations)

    merged = departure.merge(
        arrival[[config.STATION_COL, "slot_of_day", "pred"]],
        on=[config.STATION_COL, "slot_of_day"],
        how="inner",
        suffixes=("_dep", "_arr"),
    ).rename(columns={"pred_dep": "dep_pred", "pred_arr": "arr_pred"})

    columns = [config.STATION_COL, "slot_of_day", "latitude", "longitude", "dep_pred", "arr_pred"]
    return merged[columns].sort_values([config.STATION_COL, "slot_of_day"]).reset_index(drop=True)


def compute_rebalancing(
    bundles: Mapping[str, "serving.LocalTargetBundle"], **kwargs
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predict a representative day and reduce it to ranked rebalancing priorities.

    Returns ``(netflow_df, risk_df)`` where ``netflow_df`` is the per-slot long
    frame (with ``net_flow``) and ``risk_df`` is the per-station risk table
    already ranked by ``rank_priorities`` (carrying a ``priority`` column).
    Keyword args are forwarded to :func:`predict_netflow_day`.
    """
    pred_df = predict_netflow_day(bundles, **kwargs)
    netflow_df = net_flow_frame(pred_df)
    risk_df = rank_priorities(station_risk(netflow_df))
    return netflow_df, risk_df


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _format_priorities(risk_df: pd.DataFrame, top_n: int) -> str:
    head = risk_df.head(top_n).copy()
    head["deficit_time"] = head["deficit_slot"].map(serving.slot_label)
    head["surplus_time"] = head["surplus_slot"].map(serving.slot_label)
    display = head[
        [
            "priority",
            config.STATION_COL,
            "direction",
            "risk_score",
            "peak_deficit",
            "deficit_time",
            "peak_surplus",
            "surplus_time",
            "throughput",
        ]
    ].round({"risk_score": 2, "peak_deficit": 2, "peak_surplus": 2, "throughput": 1})
    return display.to_string(index=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="BIXI net-flow rebalancing priorities (no AWS).")
    parser.add_argument("--dayofweek", type=int, default=1, help="0=Mon ... 6=Sun (default 1 = Tuesday).")
    parser.add_argument("--month", type=int, default=6, help="Calendar month for the representative day.")
    parser.add_argument("--top", type=int, default=20, help="How many priorities to print.")
    parser.add_argument(
        "--write-csv",
        nargs="?",
        const=str(DEFAULT_CSV_PATH),
        default=None,
        help="Also write the full ranked priority list to a CSV (optional path).",
    )
    args = parser.parse_args(argv)

    bundles = serving.load_local_bundles()
    _, risk_df = compute_rebalancing(bundles, dayofweek=args.dayofweek, month=args.month)

    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][
        args.dayofweek % 7
    ]
    print(
        f"BIXI rebalancing priorities — representative {day_name} (month {args.month}), "
        f"{len(risk_df)} stations, neutral weather."
    )
    print(_format_priorities(risk_df, args.top))
    needs_bikes = int((risk_df["direction"] == NEEDS_BIKES).sum())
    needs_docks = int((risk_df["direction"] == NEEDS_DOCKS).sum())
    print(f"\nDirection split: {needs_bikes} stations need bikes, {needs_docks} need docks.")
    print(
        "Limitation: no dock-capacity / real-time occupancy in the trip data, so this is a "
        "relative risk ranking, not exact stockout times or fill levels."
    )

    if args.write_csv:
        out_path = Path(args.write_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        risk_df.to_csv(out_path, index=False)
        print(f"\nWrote {len(risk_df)} ranked priorities to {out_path}")


if __name__ == "__main__":
    main()
