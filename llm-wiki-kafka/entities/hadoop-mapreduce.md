# Entity: Hadoop / MapReduce / HDFS

The foundational distributed batch-processing stack — the "before" that [[apache-spark|Spark]] improved on.

- **HDFS** — shared-nothing distributed filesystem (NameNode + per-machine daemons; replication or erasure coding). Open reimplementation of Google File System.
- **MapReduce** — batch algorithm (map → sort/shuffle → reduce); stateless mapper/reducer callbacks let the framework hide fault tolerance. Join algorithms: sort-merge, broadcast hash, partitioned hash. Higher-level abstractions: Pig, Hive, Cascading.
- **Downsides** (materialization, straggler waits, redundant mappers) → motivated data-flow/DAG engines ([[apache-spark|Spark]], Flink, Tez). See [[batch-vs-stream-processing]].

Appears in: [[batch-stream-processing]]
