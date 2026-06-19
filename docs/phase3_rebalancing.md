# Phase 3 — Net-Flow Rebalancing Layer

Owner: **Othmane Zizi** (`othmane-zizi-pro`).

This phase turns the two 15-minute demand models (`departure` and `arrival`) into
an operational **rebalancing** tool. It is a post-processing / serving layer — it
adds no new training and does not touch the feature pipeline. It is the payoff of
the departure/arrival split: the two forecasts are only operationally useful
*together*, as a net flow.

## 1. What it computes

For a representative weekday, every common station is scored on its predicted
intraday occupancy swing:

```
net_flow(station, slot)   = arrival_pred - departure_pred          # + fills, - drains
cumulative(station, t)    = running sum of net_flow over the 96 daily slots
peak_deficit              = max(0, -min(cumulative))   at deficit_slot   # bikes needed
peak_surplus              = max(0,  max(cumulative))   at surplus_slot   # docks needed
net_daily                 = cumulative[-1]                               # end-of-day drift
throughput                = sum(dep_pred + arr_pred)                     # how busy
risk_score                = max(peak_deficit, peak_surplus)
direction                 = "needs bikes" if peak_deficit >= peak_surplus else "needs docks"
```

The cumulative net flow is a **relative occupancy trajectory** that starts from a
common 0 reference at the start of the day. Its deepest dip is how many bikes the
station runs short of where it started (stockout severity); its highest rise is how
much it overfills (dock-shortage severity). Stations are ranked by `risk_score`
into a **rebalancing priority list**, each tagged *needs bikes* or *needs docks*.

## 2. Why it is robust to weather

Net flow is scored under a fixed **neutral weather** vector
(`temperature_2m=18, precipitation=0, wind_speed_10m=10, relative_humidity_2m=60,
weather_code=1`). Weather mostly cancels in `arrival - departure`: rain depresses
departures and arrivals together, so the *difference* — the rebalancing pressure —
is far more stable than either flow's absolute level. This also makes the priority
list a dependable operating-pattern summary rather than a one-off forecast artifact.

## 3. Module layout (`src/bixi/rebalancing.py`)

Pure functions are split from the model-driven ones so the math is unit-testable
with synthetic data and no network:

| Function | Kind | Role |
|---|---|---|
| `net_flow_frame(pred_df)` | pure | add `net_flow = arr_pred - dep_pred` |
| `station_risk(netflow_df)` | pure | cumulate → per-station deficit/surplus/slots/direction |
| `rank_priorities(risk_df, top_n=None)` | pure | sort by `risk_score` desc + add a `priority` rank |
| `predict_netflow_day(bundles, dayofweek=1, month=6, weather=NEUTRAL_WEATHER, ...)` | model | predict dep + arr for every common station across the day |
| `compute_rebalancing(bundles, **kw)` | model | predict → net flow → ranked risk table |
| `main()` | CLI | print the top-20 priorities (optional `--write-csv`) |

The model-driven path reuses the committed serving bundles
(`bixi.streamlit_local_serving.load_local_bundles`) — each bundle's `.baselines`
are filtered to the chosen weekday, the neutral weather + month are added, the
station encoder is applied, and `model.predict` is run. No AWS is required.

```bash
PYTHONPATH=src ./.venv/bin/python -m bixi.rebalancing            # top-20 for a Tuesday
PYTHONPATH=src ./.venv/bin/python -m bixi.rebalancing --dayofweek 4 --top 30
```

## 4. Streamlit page

`app.py` (and `app_ec2.py`, which reuses the same UI over S3 artifacts) gain a
**Rebalancing Priorities** page:

* a **map** (`px.scatter_mapbox`, OpenStreetMap tiles, no token) colored by
  rebalancing need and sized by `risk_score`;
* a **ranked priority table** (top 25);
* a **per-station occupancy trajectory** (cumulative net flow over the day).

The page computes live off the cached model bundles for a selected weekday.

## 5. Honest limitation

The BIXI trip data has **no dock capacity and no real-time occupancy**, so every
station's trajectory starts from the same 0 reference. The output is therefore a
**relative** risk ranking and priority order — *which* stations to service first
and in *which* direction — **not** exact stockout clock-times or absolute fill
levels. With station dock-capacity data, the same trajectory could be anchored to
real fill levels to produce absolute stockout/overflow times; that is the natural
next step.

## 6. Tests

`tests/test_bixi_rebalancing.py` (synthetic, no network) covers the `net_flow`
sign, hand-checked `peak_deficit`/`peak_surplus` and their slots, the
`direction` rule, `rank_priorities` ordering + ranks, and the
`predict_netflow_day` / `compute_rebalancing` contract via a minimal in-memory
fake bundle.
