# Entity: Apache Parquet

A columnar storage format for the Hadoop ecosystem.

- Hierarchy: file → row groups → column chunks → pages. Columnar layout → efficient compression and column pruning.
- **Read-heavy analytical** workloads; used with [[apache-spark|Spark]] (contrast [[apache-avro|Avro]], row-oriented/write-heavy — see [[data-storage-and-formats]]).
- Underlies [[delta-lake|Delta Lake]] storage.

Appears in: [[nosql-big-data-files]], [[apache-spark]]
