# Concept: Data Storage & Formats

Where data lives once you've decided how to process it — the NoSQL models and the big-data file formats, tied back to the batch/stream split.

## Relational + NoSQL together
Real architectures mix both (**polyglot persistence**). Relational = structured, normalized, [[acid-transactions|ACID]], query-agnostic schema. NoSQL trades transactional semantics for **horizontal scalability** (via the same replication + partitioning primitives as [[distributed-systems-foundations]]) and schema flexibility for [[cloud-native-architecture|cloud-native]] / [[microservices]] systems. NoSQL modeling is **query-first** and denormalized.

## NoSQL types
Key-value, document, wide-column (row vs. column oriented), graph.

## File formats — and the batch/stream echo
- **[[apache-parquet|Parquet]]** — columnar, read-heavy **analytics**, used with [[apache-spark|Spark]]. (Batch-leaning.)
- **[[apache-avro|Avro]]** — row-oriented, write-heavy **transactions**, used with [[apache-kafka|Kafka]]; schema-on-write with a registry. (Stream-leaning — and the format for [[kafka-spark-assignment]].)
- **[[delta-lake|Delta Lake]]** — ACID + schema enforcement + time travel on Spark; **unifies batch and streaming** ([[batch-vs-stream-processing]]).
- **ORC** — columnar, ACID, built-in indexes.

The columnar-vs-row choice is the storage-layer reflection of the read-heavy (batch) vs. write-heavy (stream) tradeoff.

Sources: [[nosql-big-data-files]], [[distributed-data-systems]], [[apache-spark]]
