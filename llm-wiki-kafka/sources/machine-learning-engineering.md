# Source: Machine Learning Engineering (MLE)

One-line: Hands-on MLE lecture — tracking/logging models with MLflow, the taxonomy and detection of drift in production, and deploying/serving a model with Docker + a REST API.

Raw: `../markdown/MLE.md` (38 slides).

## Key takeaways
- **MLflow** demo: end-to-end training + logging of ML models on tabular data ([[mlflow]]).
- **[[data-drift|Drift]]** — change in data distribution that degrades a deployed model. Types: feature/covariate drift, data drift, **concept drift** (target relationship changes), dual/multi drift, prediction drift, target/label drift.
  - Concept-drift solutions: frequent retraining, weighting recent data, recency-aware splits, ensemble correction, time-series feature engineering.
- **Detection techniques**: statistical — KL divergence, **JS divergence**, **Kolmogorov-Smirnov test**, mixed-type tabular drift, **L-infinity (Chebyshev) distance** (with **Alibi-Detect** code: `KSDrift`, `TabularDrift`); model-based — train a classifier to separate reference vs. current data.
- **[[tfdv|TFDV]]** (TensorFlow Data Validation) in TFX: training-serving **skew** detection and drift detection (L-infinity for categorical, JS divergence for numeric).
- **Deploy with [[docker|Docker]]**: multi-stage Dockerfile (clone code → train → serving container), expose a **FastAPI** REST API, run locally or on [[kubernetes|Kubernetes]]; fold into the MLOps pipeline.

## Connects to
- Entities: [[mlflow]], [[data-drift]], [[tfdv]], [[docker]], [[kubernetes]]
- Concepts: [[mlops-lifecycle]], [[ml-deployment-and-serving]], [[ml-testing-and-monitoring]]
- Related sources: [[real-world-ml-in-production]], [[automl-fine-tuning]], [[cloud-native-applications]]
