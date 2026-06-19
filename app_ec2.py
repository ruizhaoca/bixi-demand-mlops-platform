"""EC2-only Streamlit entrypoint for BIXI demand prediction.

Run on EC2:
    streamlit run app_ec2.py --server.address=0.0.0.0 --server.port=8501

Deployment mode:
    EC2 Streamlit + S3 Phase-2 artifacts.

The UI is intentionally reused from ``app.py`` so the Community Cloud packaged
artifact app continues to work unchanged. This entrypoint swaps the artifact
loader to S3 and updates the sidebar deployment mode text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import app as community_app  # noqa: E402
from bixi.streamlit_local_serving import common_stations  # noqa: E402
from bixi.streamlit_s3_serving import (  # noqa: E402
    load_s3_bundles,
    load_station_clusters,
    s3_source_summary,
)


@st.cache_resource(show_spinner="Loading Phase-2 model artifacts from S3...")
def cached_s3_bundles():
    return load_s3_bundles()


@st.cache_resource(show_spinner="Loading station clusters from S3...")
def cached_s3_clusters():
    return load_station_clusters()


def render_ec2_sidebar(bundles) -> str:
    summary = s3_source_summary()
    st.sidebar.title("BIXI Demand")
    st.sidebar.caption("Mode: EC2 Streamlit + S3 Phase-2 artifacts")
    st.sidebar.caption(f"Run ID: `{summary['run_id']}`")
    st.sidebar.caption(f"Pipeline bucket: `{summary['pipeline_bucket']}`")
    st.sidebar.caption(f"Data bucket: `{summary['data_bucket']}`")
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


community_app.cached_bundles = cached_s3_bundles
community_app.cached_clusters = cached_s3_clusters
community_app.render_sidebar = render_ec2_sidebar


if __name__ == "__main__":
    community_app.main()
