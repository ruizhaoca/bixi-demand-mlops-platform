"""Streamlit app for BIXI 15-minute demand prediction.

Run locally:
    streamlit run app.py

Deployment mode:
    Streamlit Community Cloud + packaged local artifacts.

The app uses model artifacts committed under:
    artifacts/streamlit-community-cloud/cloud-2024/

It does not require AWS at runtime.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from bixi.streamlit_local_serving import (  # noqa: E402
    DEFAULT_ARTIFACT_ROOT,
    TARGET_LABELS,
    common_stations,
    load_local_bundles,
    load_station_clusters,
    slot_label,
    timestamp_for,
)


APP_TITLE = "BIXI 7-Day Demand Prediction"
MONTREAL_LAT = 45.5017
MONTREAL_LON = -73.5673
WEATHER_COLUMNS = [
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
    "weather_code",
]
WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
WEATHER_CODE_OPTIONS = list(WEATHER_CODE_DESCRIPTIONS)
SLOTS_PER_DAY = 96
PRESENTATION_DIR = REPO_ROOT / "docs" / "presentation"


st.set_page_config(page_title=APP_TITLE, layout="wide")


@st.cache_resource(show_spinner="Loading packaged model artifacts...")
def cached_bundles():
    return load_local_bundles(DEFAULT_ARTIFACT_ROOT)


@st.cache_resource(show_spinner="Loading station clusters...")
def cached_clusters():
    # Cross-target station clustering artifact; None until generated + committed.
    return load_station_clusters(DEFAULT_ARTIFACT_ROOT)


@st.cache_data(ttl=86400, show_spinner="Fetching 15-minute weather forecast...")
def fetch_weather_forecast() -> tuple[pd.DataFrame, dict]:
    """Fetch and normalize 7-day 15-minute Open-Meteo weather.

    If the API is unavailable, return a conservative default forecast so the app
    can still be demoed locally.
    """
    today = dt.date.today()
    full_index = pd.date_range(
        start=pd.Timestamp(today),
        periods=7 * SLOTS_PER_DAY,
        freq="15min",
    )
    metadata = {
        "source": "Open-Meteo",
        "fallback_used": False,
        "message": "",
        "missing_before_fill": {},
    }
    params = {
        "latitude": MONTREAL_LAT,
        "longitude": MONTREAL_LON,
        "minutely_15": ",".join(WEATHER_COLUMNS),
        "forecast_days": 7,
        "timezone": "America/Toronto",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
    }
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        minutely = payload["minutely_15"]
        weather = pd.DataFrame({"datetime": pd.to_datetime(minutely["time"])})
        for col in WEATHER_COLUMNS:
            weather[col] = minutely[col]
        metadata["source"] = "Open-Meteo 15-minute forecast"
    except Exception as exc:
        metadata["source"] = "Default fallback weather"
        metadata["fallback_used"] = True
        metadata["message"] = f"Open-Meteo request failed: {exc}"
        weather = pd.DataFrame({"datetime": full_index})
        weather["temperature_2m"] = 20.0
        weather["precipitation"] = 0.0
        weather["wind_speed_10m"] = 10.0
        weather["relative_humidity_2m"] = 60.0
        weather["weather_code"] = 0.0

    weather = (
        weather.sort_values("datetime")
        .drop_duplicates(subset=["datetime"])
        .set_index("datetime")
        .reindex(full_index)
    )
    metadata["missing_before_fill"] = {
        col: int(weather[col].isna().sum()) for col in WEATHER_COLUMNS if col in weather
    }

    for col in ["temperature_2m", "wind_speed_10m", "relative_humidity_2m"]:
        weather[col] = pd.to_numeric(weather[col], errors="coerce").interpolate().ffill().bfill()
    weather["precipitation"] = pd.to_numeric(weather["precipitation"], errors="coerce").fillna(0.0)
    weather["weather_code"] = (
        pd.to_numeric(weather["weather_code"], errors="coerce")
        .ffill()
        .bfill()
        .fillna(0.0)
        .round()
    )
    weather.index.name = "datetime"
    return weather.reset_index(), metadata


def weather_for_timestamp(weather_df: pd.DataFrame, timestamp: pd.Timestamp) -> dict:
    match = weather_df.loc[weather_df["datetime"] == timestamp]
    if match.empty:
        nearest_idx = (weather_df["datetime"] - timestamp).abs().idxmin()
        row = weather_df.loc[nearest_idx]
    else:
        row = match.iloc[0]
    return {col: float(row[col]) for col in WEATHER_COLUMNS}


def weather_for_day(weather_df: pd.DataFrame, date_value: dt.date) -> pd.DataFrame:
    rows = []
    for slot in range(SLOTS_PER_DAY):
        ts = timestamp_for(date_value, slot)
        rows.append({"datetime": ts, "slot_of_day": slot, **weather_for_timestamp(weather_df, ts)})
    return pd.DataFrame(rows)


def metric_card(label: str, value, fmt: str = "{:.3f}") -> None:
    if isinstance(value, (int, float)) and not pd.isna(value):
        st.metric(label, fmt.format(value))
    else:
        st.metric(label, "n/a")


def build_day_predictions(bundles, station_name: str, date_value: dt.date, weather_day: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame({"datetime": weather_day["datetime"], "time": weather_day["datetime"].dt.strftime("%H:%M")})
    for target, bundle in bundles.items():
        feature_rows = [
            bundle.build_feature_row(
                station_name=station_name,
                timestamp=row["datetime"],
                weather={col: row[col] for col in WEATHER_COLUMNS},
            )
            for _, row in weather_day.iterrows()
        ]
        output[TARGET_LABELS[target]] = bundle.predict_rows(feature_rows).round(3)
    return output


def date_bounds() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    return today, today + dt.timedelta(days=6)


def custom_input_date_bounds() -> tuple[dt.date, dt.date]:
    today = dt.date.today()
    return today, today + dt.timedelta(days=365)


def weather_code_label(code: int | float) -> str:
    code_int = int(round(float(code)))
    return f"{code_int} - {WEATHER_CODE_DESCRIPTIONS.get(code_int, 'Unknown weather condition')}"


def render_weather_code_reference() -> None:
    st.caption(
        "`weather_code` uses Open-Meteo/WMO condition codes. "
        "Lower values are clear or cloudy; higher grouped values represent fog, rain, snow, showers, and storms."
    )


def render_insight(text: str) -> None:
    st.info(f"Insight: {text}")


def render_weather_status(metadata: dict) -> None:
    if metadata.get("fallback_used"):
        st.warning(metadata.get("message", "Using fallback weather values."))
    else:
        st.caption(f"Weather source: {metadata.get('source', 'Open-Meteo')}. Cached for 24 hours.")

    missing = metadata.get("missing_before_fill", {})
    missing_total = sum(missing.values())
    if missing_total:
        with st.expander("Weather missing-value handling"):
            st.write("Missing values were filled with interpolation, forward/back fill, or precipitation=0.")
            st.json(missing)


def render_page_7_day_prediction(bundles) -> None:
    st.header("7-Day Demand Prediction")
    st.write(
        "Predict 15-minute BIXI station demand using packaged models and cached Open-Meteo weather."
    )

    weather_df, weather_meta = fetch_weather_forecast()
    render_weather_status(weather_meta)
    render_weather_code_reference()
    min_date, max_date = date_bounds()

    tab_single, tab_day = st.tabs(["Single Time Slot Prediction", "Prediction for a Day"])

    with tab_single:
        target = st.radio(
            "Prediction target",
            options=list(TARGET_LABELS),
            format_func=lambda value: TARGET_LABELS[value],
            horizontal=True,
            key="single_target",
        )
        bundle = bundles[target]
        col_station, col_date, col_time = st.columns([2, 1, 1])
        with col_station:
            station_name = st.selectbox("Station", bundle.stations, key="single_station")
        with col_date:
            date_value = st.date_input(
                "Date",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="single_date",
            )
        with col_time:
            slot = st.selectbox(
                "15-minute time slot",
                options=list(range(SLOTS_PER_DAY)),
                format_func=slot_label,
                index=32,
                key="single_slot",
            )

        timestamp = timestamp_for(date_value, slot)
        weather = weather_for_timestamp(weather_df, timestamp)

        st.subheader("Weather Features")
        cols = st.columns(5)
        cols[0].metric("temperature_2m", f"{weather['temperature_2m']:.1f} C")
        cols[1].metric("precipitation", f"{weather['precipitation']:.2f} mm")
        cols[2].metric("wind_speed_10m", f"{weather['wind_speed_10m']:.1f} km/h")
        cols[3].metric("relative_humidity_2m", f"{weather['relative_humidity_2m']:.0f}%")
        cols[4].metric("weather_code", weather_code_label(weather["weather_code"]))

        if st.button("Predict selected time slot", type="primary"):
            feature_row = bundle.build_feature_row(station_name, timestamp, weather)
            prediction = bundle.predict_one(feature_row)
            st.success(f"Predicted {bundle.label.lower()} demand: {prediction:.2f} trips")
            with st.expander("Engineered model features"):
                st.json(feature_row)

    with tab_day:
        stations = common_stations(bundles)
        col_station, col_date = st.columns([2, 1])
        with col_station:
            station_name = st.selectbox("Station", stations, key="day_station")
        with col_date:
            date_value = st.date_input(
                "Date",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                key="day_date",
            )

        if st.button("Predict full day", type="primary"):
            weather_day = weather_for_day(weather_df, date_value)
            day_predictions = build_day_predictions(bundles, station_name, date_value, weather_day)

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=day_predictions["time"],
                    y=day_predictions["Departure"],
                    name="Departure",
                    mode="lines",
                    line=dict(width=2, color="#b91c1c"),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=day_predictions["time"],
                    y=day_predictions["Arrival"],
                    name="Arrival",
                    mode="lines",
                    line=dict(width=2, color="#fca5a5"),
                )
            )
            fig.update_layout(
                title=f"15-minute demand prediction for {station_name} on {date_value}",
                xaxis_title="Time",
                yaxis_title="Predicted trips per 15 minutes",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig.update_xaxes(dtick=8)
            st.plotly_chart(fig, width="stretch")

            with st.expander("Prediction table"):
                st.dataframe(day_predictions, width="stretch")


def render_custom_inputs(bundles) -> None:
    st.header("Demand Prediction with Custom Inputs")
    st.write(
        "Test what-if scenarios by choosing a station, reference time, and custom weather conditions. "
    )

    target = st.radio(
        "Prediction target",
        options=list(TARGET_LABELS),
        format_func=lambda value: TARGET_LABELS[value],
        horizontal=True,
        key="custom_target",
    )
    bundle = bundles[target]

    min_date, max_date = custom_input_date_bounds()
    col_station, col_date, col_time = st.columns([2, 1, 1])
    with col_station:
        station_name = st.selectbox("Station", bundle.stations, key="custom_station")
    with col_date:
        date_value = st.date_input(
            "Reference date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            key="custom_date",
        )
    with col_time:
        slot = st.selectbox(
            "Reference 15-minute slot",
            options=list(range(SLOTS_PER_DAY)),
            format_func=slot_label,
            index=32,
            key="custom_slot",
        )

    timestamp = timestamp_for(date_value, slot)
    baseline_defaults = bundle.get_baseline_row(station_name, timestamp)

    generated_feature_names = [
        "latitude",
        "longitude",
        "dayofweek",
        "month",
        "slot_sin",
        "slot_cos",
        "hist_avg_demand",
        "baseline_prev_15min",
        "baseline_prev_1h",
        "baseline_yesterday_same_slot",
    ]
    with st.expander("Generated station, time, and historical baseline features", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {"feature": feature, "value": baseline_defaults[feature]}
                    for feature in generated_feature_names
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    st.subheader("Custom Weather Features")
    render_weather_code_reference()
    c1, c2 = st.columns(2)
    with c1:
        temperature_2m = st.slider(
            "temperature_2m",
            min_value=-30.0,
            max_value=45.0,
            value=20.0,
            step=0.5,
            help="Air temperature at 2 meters above ground, in Celsius.",
        )
        precipitation = st.number_input(
            "precipitation",
            min_value=0.0,
            max_value=50.0,
            value=0.0,
            step=0.1,
            help="Precipitation amount for the 15-minute slot, in millimeters.",
        )
    with c2:
        wind_speed_10m = st.slider(
            "wind_speed_10m",
            min_value=0.0,
            max_value=100.0,
            value=10.0,
            step=1.0,
            help="Wind speed at 10 meters above ground, in km/h.",
        )
        relative_humidity_2m = st.slider(
            "relative_humidity_2m",
            min_value=0.0,
            max_value=100.0,
            value=60.0,
            step=1.0,
            help="Relative humidity at 2 meters above ground, as a percentage.",
        )
        weather_code = st.selectbox(
            "weather_code",
            options=WEATHER_CODE_OPTIONS,
            format_func=weather_code_label,
            help="Open-Meteo/WMO weather condition code.",
        )

    weather_inputs = {
        "temperature_2m": temperature_2m,
        "precipitation": precipitation,
        "wind_speed_10m": wind_speed_10m,
        "relative_humidity_2m": relative_humidity_2m,
        "weather_code": weather_code,
    }
    feature_row = bundle.build_feature_row(station_name, timestamp, weather_inputs)

    if st.button("Predict custom scenario", type="primary"):
        prediction = bundle.predict_one(feature_row)
        st.success(f"Predicted {bundle.label.lower()} demand: {prediction:.2f} trips")
        with st.expander("Submitted feature row"):
            st.json(feature_row)


def safe_dataframe(records) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def render_metric_summary(bundle) -> None:
    metrics = bundle.metrics.get("selected", {})
    val = metrics.get("val", {})
    test = metrics.get("test", {})
    st.markdown(f"#### {bundle.label}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Best Model", bundle.metrics.get("best_model", metrics.get("name", "n/a")))
    c2.metric("Val RMSE", f"{val.get('rmse', np.nan):.3f}" if val else "n/a")
    c3.metric("Test RMSE", f"{test.get('rmse', np.nan):.3f}" if test else "n/a")
    c4.metric("Test R2", f"{test.get('r2', np.nan):.3f}" if test else "n/a")


def model_metrics_insight(bundles) -> str:
    return (
        "Both models perform similarly, with test RMSE around 1 trip per 15-minute slot. "
        "The models capture general demand patterns, while some short-term demand variation remains unexplained."
    )


def shap_insight(bundle) -> str:
    if bundle.target == "departure":
        return (
            "Recent historical demand patterns are the strongest drivers of departure predictions. "
            "Higher baseline_prev_15min and hist_avg_demand values generally push predicted departures upward, "
            "while weather and calendar features have smaller effects."
        )
    return (
        "Arrival predictions are also mainly driven by historical baseline demand features. "
        "Higher recent and average demand baselines tend to increase predicted arrivals, while temperature, "
        "month, and humidity add secondary adjustments to the prediction."
    )


def readable_fairness_flags(report: dict) -> list[str]:
    messages = []
    tier_ratio = report.get("tier_rmse_disparity_ratio")
    if isinstance(tier_ratio, (int, float)) and not pd.isna(tier_ratio):
        if tier_ratio > 1.5:
            messages.append(
                f"Prediction error is uneven across demand tiers: the hardest tier has about "
                f"{tier_ratio:.1f}x the RMSE of the easiest tier."
            )
        else:
            messages.append("Prediction error is relatively balanced across demand tiers.")

    zone_ratio = report.get("zone_rmse_disparity_ratio")
    if isinstance(zone_ratio, (int, float)) and not pd.isna(zone_ratio):
        if zone_ratio > 2:
            messages.append(
                f"Accuracy varies by geography: the highest-error zone has about "
                f"{zone_ratio:.1f}x the RMSE of the lowest-error zone."
            )
        else:
            messages.append("Geographic zones show relatively similar RMSE levels.")

    return messages or ["No major fairness warning was packaged for this target."]


def fairness_insight(bundle) -> str:
    if bundle.target == "departure":
        return (
            "Prediction accuracy varies across demand tiers and geographic zones. "
            "High-demand departure stations and several geographic areas have larger errors, "
            "so these groups should be monitored separately in future model updates."
        )
    return (
        "Arrival prediction accuracy also differs by demand tier and location. "
        "High-demand arrival stations and some geographic zones show higher errors, suggesting that future "
        "improvements should track arrival performance separately across these groups."
    )


def drift_insight(bundle) -> str:
    if bundle.target == "departure":
        return (
            "Departure demand shows clear drift signals, with 80%–87% of monitored features changing across "
            "the tested 2025 periods. However, RMSE remains around 1 trip per 15-minute slot and R² stays "
            "stable near 0.33, so this should be treated as a signal for monitoring and retraining review, "
            "not an immediate model failure."
        )
    return (
        "Arrival demand also shows strong drift signals, with about 87% of monitored features drifting in both "
        "tested periods. Model performance remains relatively stable, with RMSE around 1 trip per 15-minute "
        "slot and R² around 0.34, suggesting the model still captures general patterns but should be reviewed "
        "as new data becomes available."
    )


def render_explainability(bundles) -> None:
    st.subheader("Model Explainability")
    cols = st.columns(2)
    image_map = {
        "departure": PRESENTATION_DIR / "shap_beeswarm_departure.png",
        "arrival": PRESENTATION_DIR / "shap_beeswarm_arrival.png",
    }
    for col, (target, bundle) in zip(cols, bundles.items()):
        with col:
            st.markdown(f"#### {bundle.label}")
            if image_map[target].exists():
                st.image(str(image_map[target]), caption=f"{bundle.label} SHAP beeswarm")
            render_insight(shap_insight(bundle))


def render_fairness(bundles) -> None:
    st.subheader("Fairness Analysis")
    for target, bundle in bundles.items():
        with st.expander(f"{bundle.label} fairness report", expanded=(target == "departure")):
            report = bundle.fairness_report
            if not report:
                st.info("No fairness report packaged.")
                continue
            overall = report.get("overall", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Overall RMSE", f"{overall.get('rmse', np.nan):.3f}")
            c2.metric("Overall MAE", f"{overall.get('mae', np.nan):.3f}")
            c3.metric("Overall R2", f"{overall.get('r2', np.nan):.3f}")
            c4.metric("Tier RMSE Ratio", f"{report.get('tier_rmse_disparity_ratio', np.nan):.2f}")
            tier_df = safe_dataframe(report.get("by_demand_tier"))
            if not tier_df.empty:
                st.markdown("Demand-tier error parity")
                st.dataframe(tier_df, width="stretch")
            zones = safe_dataframe(report.get("worst_zones"))
            if not zones.empty:
                st.markdown("Worst geographic zones by RMSE")
                st.dataframe(zones.head(10), width="stretch")
            st.markdown("Reader-friendly flags")
            for flag in readable_fairness_flags(report):
                st.warning(flag)
            render_insight(fairness_insight(bundle))


def render_drift(bundles) -> None:
    st.subheader("Drift Reports")
    drift_images = [
        PRESENTATION_DIR / "drift_feature_departure_oct.png",
        PRESENTATION_DIR / "drift_concept_departure_oct.png",
    ]
    existing_images = [path for path in drift_images if path.exists()]
    if existing_images:
        cols = st.columns(len(existing_images))
        for col, image_path in zip(cols, existing_images):
            col.image(str(image_path), caption=image_path.stem.replace("_", " ").title())

    for target, bundle in bundles.items():
        with st.expander(f"{bundle.label} drift summary", expanded=(target == "departure")):
            summary = bundle.drift_summary
            if not summary:
                st.info("No drift summary packaged.")
                continue
            rows = []
            for period, values in summary.items():
                feature = values.get("feature_drift", {})
                target_drift = values.get("target_drift", {})
                prediction = values.get("prediction_drift", {})
                concept = values.get("concept_drift", {})
                rows.append(
                    {
                        "period": period,
                        "feature_drifted": feature.get("n_drifted"),
                        "feature_total": feature.get("n_features"),
                        "share_drifted": feature.get("share_drifted"),
                        "target_drift": target_drift.get("drift"),
                        "prediction_drift": prediction.get("drift"),
                        "concept_alert": concept.get("concept_drift_alert"),
                        "current_r2": concept.get("current_r2"),
                        "current_rmse": concept.get("current_rmse"),
                    }
                )
            st.dataframe(pd.DataFrame(rows), width="stretch")
            caveat = next(iter(summary.values())).get("caveat") if summary else None
            if caveat:
                st.caption(caveat)
            render_insight(drift_insight(bundle))


def render_monitoring(bundles) -> None:
    st.header("Predictive Model Monitoring")
    st.write("Packaged model metrics, explainability, fairness, and drift artifacts.")

    st.subheader("Model Metrics")
    for bundle in bundles.values():
        render_metric_summary(bundle)
    render_insight(model_metrics_insight(bundles))

    tab_explain, tab_fairness, tab_drift = st.tabs(["Explainability", "Fairness", "Drift"])
    with tab_explain:
        render_explainability(bundles)
    with tab_fairness:
        render_fairness(bundles)
    with tab_drift:
        render_drift(bundles)


def render_station_clusters(clusters) -> None:
    st.header("Station Clusters")
    st.write(
        "Operational station segments learned from cross-target (departure + arrival) "
        "15-minute demand profiles, used to flag rebalancing risk."
    )
    if clusters is None or clusters.table.empty:
        st.info(
            "Station cluster artifacts are not packaged yet. Generate them with "
            "`python -m bixi.cluster --run-id cloud-2024` and commit "
            "`artifacts/streamlit-community-cloud/cloud-2024/clusters/`."
        )
        return

    table = clusters.table.copy()
    table = table[(table["latitude"] != 0) & (table["longitude"] != 0)]
    summary = clusters.summary or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Stations", len(table))
    c2.metric("Clusters", summary.get("n_clusters", int(table["cluster"].nunique())))
    silhouette = (summary.get("scores") or {}).get("silhouette")
    c3.metric("Algorithm", summary.get("algorithm", "-"),
              f"silhouette {silhouette:.3f}" if isinstance(silhouette, (int, float)) else None)

    labels = sorted(table["cluster_label"].unique())
    chosen = st.multiselect("Filter clusters", labels, default=labels)
    view = table[table["cluster_label"].isin(chosen)] if chosen else table

    fig = px.scatter_mapbox(
        view, lat="latitude", lon="longitude", color="cluster_label",
        hover_name="station_name",
        hover_data={"demand_level": True, "rebalancing_flag": True,
                    "dep_intensity": ":.2f", "arr_intensity": ":.2f",
                    "latitude": False, "longitude": False},
        zoom=11, height=600, center={"lat": MONTREAL_LAT, "lon": MONTREAL_LON},
    )
    fig.update_layout(mapbox_style="open-street-map",
                      margin=dict(l=0, r=0, t=0, b=0), legend_title="Cluster")
    st.plotly_chart(fig, width="stretch")

    agg = (
        table.groupby(["cluster_label", "demand_level", "rebalancing_flag"])
        .agg(stations=("station_name", "count"),
             dep_intensity=("dep_intensity", "mean"),
             arr_intensity=("arr_intensity", "mean"))
        .reset_index().sort_values("stations", ascending=False)
    )
    st.subheader("Cluster summary")
    st.dataframe(agg, width="stretch")
    render_insight(
        "Departure-heavy clusters tend to be commuter-origin (residential) stations that "
        "empty in the morning; arrival-heavy clusters are commuter destinations (downtown/"
        "campus) that fill up — the pairing drives rebalancing priorities."
    )


def render_sidebar(bundles) -> str:
    st.sidebar.title("BIXI Demand")
    st.sidebar.caption("Mode: Streamlit Community Cloud packaged local artifacts")
    st.sidebar.caption(f"Artifact root: `{DEFAULT_ARTIFACT_ROOT}`")
    total_stations = len(common_stations(bundles))
    st.sidebar.metric("Common Stations", total_stations)
    return st.sidebar.radio(
        "Page",
        [
            "7-Day Demand Prediction",
            "Demand Prediction with Custom Inputs",
            "Station Clusters",
            "Predictive Model Monitoring",
        ],
    )


def main() -> None:
    st.title(APP_TITLE)
    bundles = cached_bundles()
    page = render_sidebar(bundles)

    if page == "7-Day Demand Prediction":
        render_page_7_day_prediction(bundles)
    elif page == "Demand Prediction with Custom Inputs":
        render_custom_inputs(bundles)
    elif page == "Station Clusters":
        render_station_clusters(cached_clusters())
    else:
        render_monitoring(bundles)

    st.divider()
    st.caption(
        "Predictions use 15-minute departure and arrival demand models trained on 2024 data, "
        "with 2024 historical baselines recomputed for future serving without leave-one-out."
    )


if __name__ == "__main__":
    main()
