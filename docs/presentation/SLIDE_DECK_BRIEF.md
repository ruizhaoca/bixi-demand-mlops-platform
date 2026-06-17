# Slide Deck Brief — BIXI Demand MLOps Platform (final presentation)

This is the single reference for building the final presentation deck. It assumes
**all four phases are done** (Phase 3 clustering + Phase 4 Streamlit are Rui's — draft
those slides from the intent below and mark them `[CONFIRM w/ Rui]` so real
numbers/screenshots can be swapped in).

## Required structure — EnterpriseDataScience **Section 5.9 Solution Presentation**
The professor grades the talk against this map (see `INSY684 Group Project/5.9. Solution Presentation Map.png`):
**Context · Hypothesis · Data · Model (Modelling Approach + Model Evaluation) · Results · Explainability of Results · Threats to Validity · Conclusion · Lessons Learned & Next Steps.**
Plus the mandatory submission slide: **team name, every member + GitHub id, repo name.**

## Logistics
- **7–8 minutes, four presenters**, ~1.5–2 min each. Speaker notes on every slide.
- Output an **editable PowerPoint** so the team can finish it in PowerPoint Cloud:
  generate `docs/presentation/bixi_mlops_deck.pptx` with **python-pptx**
  (`pip install python-pptx`), 16:9, with **speaker notes per slide**, embedding the
  PNGs already in `docs/presentation/` (see Assets). ~14 slides.
- Presenter flow (agreed in the group chat):
  - **Sarah Liu + Ruihe "Louis" Zhang** → project intro · AWS/productionized structure · data cleaning, EDA, feature engineering
  - **Othmane Zizi** → the full predictive-modeling part
  - **Rui Zhao** → clustering · Streamlit app · meaning, limitations & conclusion

## Team (for the mandatory slide)
| Name | GitHub id | Part |
|---|---|---|
| Othmane Zizi | `othmane-zizi-pro` | Phase 2 — predictive modeling, MLflow, explainability, fairness, drift, AWS CDK infra |
| Ruihe Zhang (Louis) | `mudkipython` | Phase 1 — data + feature engineering |
| Sarah Liu | `[CONFIRM handle]` (GitHub email chih-hsuan.liu@mail.mcgill.ca) | Phase 1 — setup, cleaning, EDA |
| Rui Zhao | `ruizhaoca` | Phase 3 clustering + Phase 4 Streamlit/serving |
- **Repo:** `bixi-demand-mlops-platform` — https://github.com/ruizhaoca/bixi-demand-mlops-platform
- **Team name:** `[CONFIRM]` — none fixed; propose e.g. "BIXI MLOps" (chat group is "INSY684 Group").
- **Course footer:** `[CONFIRM 684 vs 695]` — files say INSY684; plan.md says INSY 695.

## Slide outline (maps every 5.9 section)
1. **Title** — team name, 4 members + GitHub ids, repo name. *(mandatory)*
2. **Context / business problem** *(Sarah+Louis)* — BIXI rebalancing; two failure modes: stations run **out of bikes** (can't rent) vs **out of docks** (can't return); operators must pre-position bikes. Course-1 baseline app: hourly, total demand, top-400 stations, single LightGBM, on Streamlit Cloud, no MLOps.
3. **Hypothesis / objective** *(Sarah+Louis)* — finer, split, station-level demand prediction lets BIXI anticipate both failure modes. Improvements vs course-1: **15-min (4× resolution)**, **departures *and* arrivals** separately, **all ~1,100+ stations**, leakage-safe lagged features, **multi-model + AutoML**, full production MLOps.
4. **Data** *(Sarah+Louis)* — sources: BIXI open data (2024 + 2025) + Open-Meteo 15-min weather; splits **train 2024 / val May-2025 / test Oct-2025**; cleaning; **advanced imputation (KNN/MICE)**; 15-min aggregation per station; **leakage-safe** historical baselines + lags + advanced encoding; data dictionary. Feature schema (18 cols) in `docs/phase2_modeling.md`.
5. **Production architecture (AWS, all via CDK)** *(Sarah+Louis)* — diagram: GitHub → CDK provisions VPC, S3, **MLflow on EC2+S3**, **ECR image + AWS Batch** (cloud training); one command runs/resumes the pipeline. (Use the architecture description in `docs/phase2_modeling.md` §5.)
6. **Modelling approach** *(Othmane — 5.9 Model)* — one resumable pipeline run per target; **baseline → LightGBM (L2/Poisson/Tweedie) + XGBoost + HistGB → FLAML AutoML → Optuna HPO**, auto-select by val RMSE; **MLflow tracking + Model Registry (`production` alias)**; stages `ingest→data→train→explain→fairness→drift→register`.
7. **Results / model evaluation** *(Othmane — 5.9 Model Evaluation + Results)* — table below; emphasize beating the historical-average baseline; embed `mlflow_departure_runs.png` (73 runs) + `mlflow_model_departure.png` (`@production`).
8. **Explainability** *(Othmane — 5.9 Explainability)* — SHAP global+local + LIME; top drivers = recent lag + historical baseline + weather; embed `shap_beeswarm_departure.png`.
9. **Responsible AI — fairness + drift** *(Othmane)* — error-parity across demand tiers/zones (numbers below); **4-type Evidently drift** with the honest **2024-baseline caveat (no live cron)**; embed `drift_feature_departure_oct.png`.
10. **Clustering** *(Rui — Phase 3) `[CONFIRM w/ Rui]`* — compare K-Means vs GMM/Agglomerative/DBSCAN, auto-select by silhouette/Davies-Bouldin/Calinski-Harabasz; **operational clusters**: group stations by departure/arrival intensity across **morning rush / evening rush / other** to flag rebalancing risk (high-departure-low-arrival); `station_clusters.csv`; cluster feature-drift (assignment stability, centroid shift).
11. **Serving & app** *(Rui — Phase 4) `[CONFIRM w/ Rui]`* — FastAPI + **Streamlit on ECS Fargate behind an ALB**; pages: 16-day forecast, custom input, clusters map (PyDeck), Explainability (SHAP), Monitoring (drift). Live demo. *(Note: a 15-min inference contract exists in `src/bixi/inference.py`; the live endpoint is Rui's Phase 4.)*
12. **Threats to validity** *(Othmane/Rui — 5.9)* — 15-min demand is zero-inflated & noisy → R² in low-0.3s is the honest ceiling (vs course-1 hourly 0.63, an easier aggregated target); **2024 is baseline for all years** (limits drift realism); a 2024↔2025 timezone-offset nuance to confirm; Phase-1 date-range spillover (handled at load + clean copies in S3).
13. **Conclusion** *(Rui — 5.9)* — we turned a course-1 notebook app into a production MLOps platform: cloud-trained, tracked, explainable, fair, monitored, IaC-deployed.
14. **Lessons learned & next steps** *(Rui — 5.9)* — entity embeddings/PCA; richer/real-time data when BIXI exposes it; scheduled retraining + live drift cron once fresh labels exist; A/B + canary serving; cost controls.

## Final results to put on the slides (run `cloud-2024`, full data, all stations)
| target | selected | val R² | val RMSE | test R² | test RMSE | baseline val R² |
|---|---|---|---|---|---|---|
| departure | Optuna-tuned LightGBM | 0.327 | 0.994 | 0.334 | 1.035 | 0.263 |
| arrival | Optuna-tuned LightGBM | 0.339 | 0.976 | 0.339 | 1.026 | 0.268 |
- MLflow: **73 departure + 57 arrival runs**; both registered with the **`production`** alias.
- Top SHAP features (both): `baseline_prev_15min`, `hist_avg_demand`, `temperature_2m`, `month`, `relative_humidity_2m`.
- Fairness disparity (worst/best RMSE): departure **tier 2.39× / zone 16.0×**, arrival **tier 2.35× / zone 14.1×**. By tier (departure): high RMSE 1.41 (R² 0.39), medium 0.92 (0.07), low 0.59 (0.02) — note zero-inflation: quiet stations have low absolute error but little variance to explain.
- Drift: feature 13/15 (May) & 12/15 (Oct) columns flag; target + concept flagged — under the 2024-baseline caveat.

## Assets to embed (already in `docs/presentation/`)
`mlflow_departure_runs.png`, `mlflow_arrival_runs.png`, `mlflow_run_detail_departure.png`,
`mlflow_model_registry.png`, `mlflow_model_departure.png` (shows `@production`),
`drift_feature_departure_oct.png`, `drift_concept_departure_oct.png`,
`shap_beeswarm_departure.png`, `shap_beeswarm_arrival.png`.
More SHAP/LIME/drift artifacts: `~/bixi_presentation/<target>/{explain,drift}/`.
Live MLflow (until June 19): http://3.18.229.78:5000 (Models → `@production`).

## Open items to confirm before finalizing
- Sarah's GitHub handle; the team name; course number (684 vs 695) for the footer.
- Rui's real clustering metrics + Streamlit screenshots (slides 10–11 are drafted from intent).

## Reference docs
`docs/phase2_modeling.md` (design + architecture + data caveats), root `README.md`
(S3 asset map), `plan.md` (master plan), `instructions_final_project_presentation.md`.
