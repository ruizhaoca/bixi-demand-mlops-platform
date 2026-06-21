"""Small no-network checks for memory-efficient S3 serving artifacts."""

import pandas as pd

from bixi.streamlit_s3_serving import _compact_s3_baselines


def test_compact_s3_baselines_uses_category_and_float32():
    frame = pd.DataFrame(
        {
            "station_name": ["A", "A", "B"],
            "latitude": [45.5, 45.5, 45.6],
            "longitude": [-73.5, -73.5, -73.6],
        }
    )
    compact = _compact_s3_baselines(frame)
    assert isinstance(compact["station_name"].dtype, pd.CategoricalDtype)
    assert compact["latitude"].dtype == "float32"
    assert compact["longitude"].dtype == "float32"

