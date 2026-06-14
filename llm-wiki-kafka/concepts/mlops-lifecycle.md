# Concept: MLOps Lifecycle

How DevOps discipline extends to ML — the spine of Modules III–IV.

## DevOps → DataOps → MLOps
ML adds, on top of DevOps: data→model **reproducibility**, model **validation** (A/B), **versioning & lineage** (track a model's evolution), and deployment/monitoring across cloud + edge. The *Hidden Technical Debt in ML* framing motivates it.

## The lifecycle
**Experiment → Develop → Operate** (data acquisition → modelling/testing → CI/CD → monitoring). Two goals: **repeatable experiments** and **managing the model lifecycle**. Reference architectures from Microsoft & AWS mature through initial → repeatable → reliable → scalable phases.

## Version everything
Source code, datasets, models, and experiment runs — for reproducibility and governance. Tooling: [[mlflow|MLflow]] (Tracking / Projects / Models / Registry), Poetry, Cookiecutter.

## Connections
- Inherits CI/CD, containers, and orchestration from [[cloud-native-architecture]] ([[docker]], [[kubernetes]]).
- Inherits engineering discipline from [[software-engineering-best-practices]].
- Operate phase = [[ml-deployment-and-serving]] + [[ml-testing-and-monitoring]] (incl. [[data-drift]]).
- HPO/model search is automated via [[automl-and-tuning]].

Sources: [[real-world-ml-in-production]], [[machine-learning-engineering]], [[cloud-native-applications]], [[syllabus]]
