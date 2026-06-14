# Entity: Apache Spark

A unified analytics engine for large-scale data — the processing side of the [[kafka-spark-assignment]].

- Modules: SQL/DataFrames, MLlib, GraphX, Spark Streaming. Runs 100× faster than [[hadoop-mapreduce|Hadoop]] via in-memory DAG execution; a **data-flow engine**.
- Cluster = one driver + many executor JVMs. APIs: **RDD** (lineage, fault-tolerant) → **DataFrame** (columnar, Catalyst/Tungsten-optimized) → Dataset.
- Reads [[apache-parquet|Parquet]]/JSON/text; underpins [[delta-lake|Delta Lake]]. Uses **micro-batching**, so it spans [[batch-vs-stream-processing|batch and stream]].
- Runs managed on [[databricks|Databricks]]. Serves [[mlflow|MLflow]] models for batch inference.

Appears in: [[apache-spark]] (source), [[batch-stream-processing]], [[syllabus]], [[machine-learning-engineering]]
