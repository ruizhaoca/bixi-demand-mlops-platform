# Entity: MLflow

The open-source platform for managing the ML lifecycle — the central tool of [[mlops-lifecycle]].

- **Tracking** — log params, metrics, artifacts, code version per *run*; UI to compare runs.
- **Projects** — reproducible packaging (conda/docker env + entry points).
- **Models** — standard packaging with "flavors"; serve via REST or batch-infer on [[apache-spark|Spark]].
- **Model Registry** — centralized store with lineage, versioning, stage transitions (staging→production).
- Integrates with [[databricks|Databricks]] and with HyperOpt for tracked HPO ([[automl-and-tuning]]).

Appears in: [[real-world-ml-in-production]], [[machine-learning-engineering]], [[automl-fine-tuning]]
