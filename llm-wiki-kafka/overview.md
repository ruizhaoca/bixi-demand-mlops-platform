# Overview — INSY 695: Enterprise Data Science & ML in Production II

The synthesis page for the whole course. See [[index]] for the full catalog.

## The through-line

The course answers one question: **how do enterprises ship and operate ML systems reliably at scale?** It builds bottom-up, from the data infrastructure underneath models to the governance practices around them.

1. **Data infrastructure** — How data moves and lives. [[batch-vs-stream-processing]] (batch vs. near-real-time, [[lambda-kappa-architecture|Lambda/Kappa]]), the [[distributed-systems-foundations|distributed systems]] that make it reliable ([[cap-theorem|CAP]], [[acid-transactions|ACID]], replication, [[consensus-algorithms|consensus]]), and [[data-storage-and-formats|where data is stored]] (NoSQL, [[apache-parquet|Parquet]], [[apache-avro|Avro]], [[delta-lake|Delta Lake]]). Tools: [[apache-spark|Spark]], [[apache-kafka|Kafka]], [[hadoop-mapreduce|Hadoop]].

2. **Deployment substrate** — Where systems run. [[cloud-native-architecture]]: [[docker|containers]], [[kubernetes|orchestration]], [[microservices]], [[twelve-factor-app|12-factor]], CI/CD — and the [[software-engineering-best-practices|engineering discipline]] underneath it all.

3. **The ML lifecycle** — How models get built, shipped, and kept alive. [[mlops-lifecycle|MLOps]] (reproducibility, versioning, [[mlflow|MLflow]]), [[ml-deployment-and-serving|deployment & serving]], [[ml-testing-and-monitoring|testing & monitoring]] including [[data-drift|drift]], and [[automl-and-tuning|AutoML/HPO]].

4. **Responsible AI** — Whether you *should* trust the model. [[responsible-ai]]: [[model-explainability|explainability]] ([[shap|SHAP]], [[lime|LIME]]), [[fairness-bias-ml|fairness & bias]], and [[securing-ml-applications|security]] ([[owasp-top-10|OWASP]], [[adversarial-ml-attacks|adversarial attacks]]).

## The recurring spine

A few ideas reappear across nearly every deck and bind the course together:

- **Bounded vs. unbounded data** — the batch/stream split ([[batch-vs-stream-processing]]) recurs in storage ([[apache-parquet|Parquet]] for read-heavy analytics vs. [[apache-avro|Avro]] for write-heavy streaming), in [[delta-lake|Delta Lake's]] batch/stream unification, and in how models are trained and served ([[ml-deployment-and-serving]]).
- **Scalability via shared-nothing** — replication + partitioning ([[distributed-systems-foundations]]) underpins [[hadoop-mapreduce|HDFS]], NoSQL ([[data-storage-and-formats]]), and [[apache-kafka|Kafka's]] partitions.
- **Reproducibility & automation** — from [[software-engineering-best-practices|SE practices]] to CI/CD ([[cloud-native-architecture]]) to MLOps ([[mlops-lifecycle]]); the same DevOps DNA flows into ML.
- **Trust** — [[ml-testing-and-monitoring|monitoring]], [[model-explainability|explainability]], [[fairness-bias-ml|fairness]], and [[securing-ml-applications|security]] are all answers to "can we trust this model in production?"

## The capstone

[[kafka-spark-assignment]] (Individual Assignment 1) is the course's first hands-on artifact and a concrete instance of Module I: produce an event stream into [[apache-kafka|Kafka]] on [[confluent-cloud|Confluent]] with an [[apache-avro|Avro]] schema, then consume and process it (batch + streaming) in [[apache-spark|Spark]] on [[databricks|Databricks]].

Sources: [[syllabus]] defines the arc; the rest are the lecture decks.
