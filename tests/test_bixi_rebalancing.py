"""Unit tests for the net-flow rebalancing layer (synthetic data, no network)."""

import numpy as np
import pandas as pd
import pytest

from bixi import config, rebalancing


def _pred_df() -> pd.DataFrame:
    """Three hand-checkable stations on a 4-slot day (slots 10/20/30/40).

    drain   : departures lead in the AM -> trajectory dips to -7 at slot 20.
    fill    : arrivals lead in the AM   -> trajectory peaks at +9 at slot 20.
    balanced: dep == arr everywhere     -> zero net flow all day.
    Rows are intentionally shuffled to exercise the slot-ordering in station_risk.
    """
    rows = [
        # station, slot, lat, lon, dep_pred, arr_pred
        ("drain", 30, 45.5, -73.5, 1, 3),
        ("drain", 10, 45.5, -73.5, 5, 1),
        ("drain", 40, 45.5, -73.5, 1, 4),
        ("drain", 20, 45.5, -73.5, 4, 1),
        ("fill", 40, 45.6, -73.6, 4, 1),
        ("fill", 10, 45.6, -73.6, 1, 6),
        ("fill", 20, 45.6, -73.6, 1, 5),
        ("fill", 30, 45.6, -73.6, 3, 1),
        ("balanced", 10, 45.7, -73.7, 2, 2),
        ("balanced", 20, 45.7, -73.7, 2, 2),
        ("balanced", 30, 45.7, -73.7, 2, 2),
        ("balanced", 40, 45.7, -73.7, 2, 2),
    ]
    return pd.DataFrame(
        rows,
        columns=[config.STATION_COL, "slot_of_day", "latitude", "longitude", "dep_pred", "arr_pred"],
    )


def test_net_flow_frame_sign_and_purity():
    pred = _pred_df()
    out = rebalancing.net_flow_frame(pred)
    # net_flow = arrival - departure (positive = filling, negative = draining).
    assert out["net_flow"].tolist() == (out["arr_pred"] - out["dep_pred"]).tolist()
    drain_am = out[(out[config.STATION_COL] == "drain") & (out["slot_of_day"] == 10)]
    fill_am = out[(out[config.STATION_COL] == "fill") & (out["slot_of_day"] == 10)]
    assert drain_am["net_flow"].iloc[0] == -4  # 1 - 5
    assert fill_am["net_flow"].iloc[0] == 5  # 6 - 1
    # The pure function must not mutate its input.
    assert "net_flow" not in pred.columns


def test_station_risk_peaks_slots_and_direction():
    risk = rebalancing.station_risk(rebalancing.net_flow_frame(_pred_df()))
    assert list(risk.columns) == rebalancing.RISK_COLUMNS
    by_station = risk.set_index(config.STATION_COL)

    # drain: cumulative [-4,-7,-5,-2] over slots [10,20,30,40].
    drain = by_station.loc["drain"]
    assert drain["peak_deficit"] == pytest.approx(7.0)
    assert drain["deficit_slot"] == 20
    assert drain["peak_surplus"] == pytest.approx(0.0)  # clipped at the day-start 0 reference
    assert drain["surplus_slot"] == 40
    assert drain["net_daily"] == pytest.approx(-2.0)
    assert drain["throughput"] == pytest.approx(20.0)
    assert drain["risk_score"] == pytest.approx(7.0)
    assert drain["direction"] == rebalancing.NEEDS_BIKES

    # fill: cumulative [5,9,7,4] over slots [10,20,30,40].
    fill = by_station.loc["fill"]
    assert fill["peak_surplus"] == pytest.approx(9.0)
    assert fill["surplus_slot"] == 20
    assert fill["peak_deficit"] == pytest.approx(0.0)
    assert fill["deficit_slot"] == 40
    assert fill["net_daily"] == pytest.approx(4.0)
    assert fill["throughput"] == pytest.approx(22.0)
    assert fill["risk_score"] == pytest.approx(9.0)
    assert fill["direction"] == rebalancing.NEEDS_DOCKS

    # balanced: no net flow -> zero risk; the deficit>=surplus tie resolves to "needs bikes".
    balanced = by_station.loc["balanced"]
    assert balanced["risk_score"] == pytest.approx(0.0)
    assert balanced["direction"] == rebalancing.NEEDS_BIKES


def test_rank_priorities_ordering_and_top_n():
    risk = rebalancing.station_risk(rebalancing.net_flow_frame(_pred_df()))
    ranked = rebalancing.rank_priorities(risk)
    # Sorted by risk_score desc: fill (9) > drain (7) > balanced (0).
    assert ranked[config.STATION_COL].tolist() == ["fill", "drain", "balanced"]
    assert ranked["priority"].tolist() == [1, 2, 3]
    assert ranked["risk_score"].is_monotonic_decreasing

    top = rebalancing.rank_priorities(risk, top_n=2)
    assert len(top) == 2
    assert top[config.STATION_COL].tolist() == ["fill", "drain"]


# --------------------------------------------------------------------------- #
# Model-driven path exercised with a minimal in-memory fake bundle (no network).
# --------------------------------------------------------------------------- #
class _FakeEncoder:
    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        out["station_freq"] = 0.5
        out["station_target_enc"] = 1.0
        return out


class _FakeModel:
    """Predicts the row's hist_avg_demand, so dep/arr differ per bundle."""

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return features["hist_avg_demand"].to_numpy(dtype="float64")


class _FakeBundle:
    def __init__(self, hist_by_station: dict[str, float]):
        slots = [10, 20, 30]
        rows = []
        for station, hist in hist_by_station.items():
            for dow in (0, 1):  # include a non-target day to test filtering
                for slot in slots:
                    rows.append(
                        {
                            config.STATION_COL: station,
                            "dayofweek": dow,
                            "slot_of_day": slot,
                            "latitude": 45.5,
                            "longitude": -73.5,
                            "slot_sin": 0.0,
                            "slot_cos": 1.0,
                            "hist_avg_demand": hist,
                            "baseline_prev_15min": hist,
                            "baseline_prev_1h": hist,
                            "baseline_yesterday_same_slot": hist,
                        }
                    )
        self.baselines = pd.DataFrame(rows)
        self.encoder = _FakeEncoder()
        self.model = _FakeModel()

    @property
    def stations(self):
        return sorted(self.baselines[config.STATION_COL].unique())


def test_predict_netflow_day_contract_and_compute():
    bundles = {
        "departure": _FakeBundle({"A": 2.0, "B": 1.0, "DEP_ONLY": 9.0}),
        "arrival": _FakeBundle({"A": 1.0, "B": 3.0}),
    }
    pred = rebalancing.predict_netflow_day(bundles, dayofweek=1, month=6)

    assert list(pred.columns) == [
        config.STATION_COL, "slot_of_day", "latitude", "longitude", "dep_pred", "arr_pred"
    ]
    # Restricted to stations common to both bundles (DEP_ONLY dropped).
    assert set(pred[config.STATION_COL]) == {"A", "B"}
    # Only the requested weekday's slots survive (3 slots x 2 stations).
    assert len(pred) == 6

    a_row = pred[pred[config.STATION_COL] == "A"].iloc[0]
    assert a_row["dep_pred"] == pytest.approx(2.0)
    assert a_row["arr_pred"] == pytest.approx(1.0)

    netflow_df, risk_df = rebalancing.compute_rebalancing(bundles, dayofweek=1, month=6)
    assert "net_flow" in netflow_df.columns
    assert "priority" in risk_df.columns
    # A drains (arr<dep -> needs bikes); B fills (arr>dep -> needs docks).
    directions = risk_df.set_index(config.STATION_COL)["direction"].to_dict()
    assert directions["A"] == rebalancing.NEEDS_BIKES
    assert directions["B"] == rebalancing.NEEDS_DOCKS
