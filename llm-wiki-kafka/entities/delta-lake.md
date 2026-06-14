# Entity: Delta Lake

A storage layer bringing reliability to data lakes on [[apache-spark|Spark]].

- **[[acid-transactions|ACID]] transactions** with serializable isolation; scalable metadata.
- **Batch + streaming unification**: one table is both a batch table and a streaming source/sink — a concrete instance of [[batch-vs-stream-processing]].
- Schema enforcement; **time travel** (data versioning → rollbacks, audit, reproducible ML); upserts/deletes (CDC, SCD). Built on [[apache-parquet|Parquet]].
- Native to [[databricks|Databricks]].

Appears in: [[nosql-big-data-files]], [[data-storage-and-formats]]
