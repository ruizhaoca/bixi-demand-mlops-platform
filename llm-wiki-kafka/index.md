# Index — INSY 695 Wiki

Catalog of every page. Start at [[overview]] for the synthesis. See [[CLAUDE]] for the schema and [[log]] for history.

## Sources (14)
- [[apache-spark|Apache Spark — An Intro]] — Spark engine, cluster model, RDD/DataFrame APIs.
- [[batch-stream-processing|Batch & Stream Processing]] — the anchor lecture; batch vs. stream, Lambda/Kappa, Kafka/ksqlDB.
- [[kafka-cheat-sheet|Kafka Cheat Sheet]] — local Kafka CLI command reference.
- [[distributed-data-systems|Distributed Data Systems]] — replication, partitioning, transactions, CAP, consensus.
- [[nosql-big-data-files|NoSQL & Big Data Files]] — NoSQL models + Parquet/Avro/Delta/ORC formats.
- [[cloud-native-applications|Cloud Native Applications]] — Docker, Kubernetes, CI/CD, 12-Factor, service mesh.
- [[software-engineering-best-practices|SE Best Practices]] — clean code, SOLID, testing.
- [[machine-learning-engineering|Machine Learning Engineering (MLE)]] — MLflow, drift, Docker serving.
- [[real-world-ml-in-production|Real-world ML in Production]] — MLOps, ML testing, MLflow components.
- [[automl-fine-tuning|AutoML & Fine-Tuning]] — HPO, Bayesian opt, NAS, gradient boosting.
- [[model-explainability|Model Explainability]] — XAI, SHAP/LIME, transparency.
- [[fairness-bias-ml|Fairness & Bias in ML]] — bias types, discrimination, fairness interventions.
- [[securing-ml-applications|Securing ML Applications]] — OWASP, adversarial attacks, defenses.
- [[syllabus|INSY 695 Syllabus]] — course map, tools, evaluation.

## Concepts (10)
- [[batch-vs-stream-processing]] — bounded vs. unbounded data; the course's central dichotomy.
- [[distributed-systems-foundations]] — replication/partitioning/CAP/ACID/consensus.
- [[data-storage-and-formats]] — NoSQL + file formats; columnar vs. row.
- [[cloud-native-architecture]] — containers, orchestration, the deployment substrate.
- [[mlops-lifecycle]] — DevOps→MLOps, versioning, reproducibility.
- [[ml-deployment-and-serving]] — packaging, REST/batch, A/B rollout.
- [[ml-testing-and-monitoring]] — seven test types + drift/skew detection.
- [[automl-and-tuning]] — AutoML, HPO, NAS, boosting.
- [[responsible-ai]] — explainability + fairness + security as one trust cluster.
- [[kafka-spark-assignment]] — Individual Assignment 1 (the live artifact).

## Entities (26)
**Streaming/data tools**: [[apache-kafka]], [[apache-spark]], [[confluent-cloud]], [[databricks]], [[ksqldb]], [[hadoop-mapreduce]], [[lambda-kappa-architecture]]
**Storage/formats**: [[apache-avro]], [[apache-parquet]], [[delta-lake]]
**Distributed-systems theory**: [[cap-theorem]], [[acid-transactions]], [[consensus-algorithms]]
**Cloud-native**: [[docker]], [[kubernetes]], [[microservices]], [[twelve-factor-app]]
**ML engineering**: [[mlflow]], [[tfdv]], [[data-drift]]
**AutoML**: [[bayesian-optimization]], [[gradient-boosting]]
**Responsible AI**: [[shap]], [[lime]], [[owasp-top-10]], [[adversarial-ml-attacks]]

## Lint candidates (for a future pass)
- **Gaps with no own page** (mentioned but not yet expanded): CDC/Debezium, Istio/service mesh, Kubeflow, differential privacy, Cookiecutter/Poetry toolchain, NAS algorithms (AdaNet/MorphNet), Alibi-Detect.
- **Thin sources by design**: slide decks are terse; [[model-explainability]] and [[fairness-bias-ml]] could gain a comparison table.
- **Potential merge**: [[ml-deployment-and-serving]] and [[ml-testing-and-monitoring]] both branch off [[mlops-lifecycle]] — fine as-is, but watch for overlap.
