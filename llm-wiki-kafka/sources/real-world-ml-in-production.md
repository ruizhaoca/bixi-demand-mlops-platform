# Source: Real-world ML in Production

One-line: The MLOps lecture — DevOps/DataOps/MLOps, the data-science project toolchain, the seven kinds of ML testing, model management with MLflow, and Jupyter notebook best practices.

Raw: `../markdown/Real-worldMLInProduction.md` (78 slides). Frames around *Hidden Technical Debt in ML Systems*.

## Key takeaways
- **DevOps → MLOps**: ML adds challenges of data→model reproducibility, model validation/A-B, storage & versioning (lineage), deployment across cloud + edge. The **MLOps lifecycle** = Experiment → Develop → Operate. Two goals: repeatable experiments + managing the model lifecycle. Reference architectures from Microsoft and AWS (initial → repeatable → reliable → scalable phases).
- **Versioning everything**: source control, dataset versioning, model versioning, experiment tracking → reproducibility + governance.
- **Data-science toolchain**: PyCharm, Poetry (env + `poetry.lock` for deterministic builds), Cookiecutter Data Science project structure.
- **Seven test types**: unit, **data tests** (schema), model validation, model performance, integration, **data skew** tests, load tests.
- **[[mlflow|MLflow]] components**: Tracking (runs: params/metrics/artifacts), Projects (reproducible packaging), Models (flavors, REST/Spark serving), Model Registry (lineage, versions, stage transitions).
- **Notebook tooling**: nteract, ReviewNB (notebook diffs/reviews), papermill (parameterized execution), treon (notebook unit tests).

## Connects to
- Entities: [[mlflow]], [[kubernetes]], [[docker]]
- Concepts: [[mlops-lifecycle]], [[ml-testing-and-monitoring]], [[ml-deployment-and-serving]]
- Related sources: [[machine-learning-engineering]], [[software-engineering-best-practices]], [[cloud-native-applications]]
