# Concept: ML Deployment & Serving

Getting a trained model into production and answering requests — the "Operate" half of [[mlops-lifecycle]].

## Frequency spectrum (the batch/stream echo)
Prediction can be **offline/batch**, **near-real-time**, or **real-time** — the same bounded/unbounded split as [[batch-vs-stream-processing]]. [[mlflow|MLflow Models]] can serve via REST or batch-infer on [[apache-spark|Spark]].

## The container path
Package the model in a [[docker|Docker]] container (multi-stage: clone → train → serving image), expose a **REST API** (FastAPI), run anywhere containers run, scale on [[kubernetes|Kubernetes]]. Kubeflow runs ML workflows on K8s. This is the same substrate as [[cloud-native-architecture]].

## Safe rollout
Validate before deploy, ramp traffic via **A/B testing**, capture telemetry (health, inputs/outputs), control rollout, optimize/quantize for the target (cloud / mobile / edge). Governance + compliance throughout.

## Connections
- Models come from [[mlops-lifecycle]] and [[automl-and-tuning]].
- Once live, watched by [[ml-testing-and-monitoring]] (drift, skew, load).

Sources: [[machine-learning-engineering]], [[real-world-ml-in-production]], [[cloud-native-applications]]
