# Source: NoSQL Data Stores and Big Data Files

One-line: When and why to use NoSQL over relational databases, the four NoSQL data models, and the big-data file formats (Parquet, Delta Lake, Avro, ORC).

Raw: `../markdown/NoSQLDataStores_BigDataFiles.md` (59 slides).

## Key takeaways
- **Relational DBs** shine with structured data, normalization, transactions, [[acid-transactions|ACID]]. Real architectures **mix relational + NoSQL** (polyglot persistence).
- **Why NoSQL**: [[cloud-native-architecture|cloud-native]] needs greater scalability, open source, dynamic/expressive schemas, escape from object-relational impedance mismatch. Benefits: flexibility, horizontal scalability, agility, HA, performance, fit for [[microservices]] / event-driven.
- Scalability via replication + partitioning (sharding/vertical/functional) — same primitives as [[distributed-systems-foundations]]. NoSQL trades transactional semantics/referential integrity for horizontal scale.
- **Data modeling**: relational = data-first, normalized, query-agnostic; non-relational = **query-first**, denormalized, single-lookup retrieval.
- **NoSQL types**: key-value, document, wide-column (row vs. column oriented), graph (+ graph algorithms for AI).
- **Big data file formats**: [[apache-parquet|Parquet]] (columnar, read-heavy analytics, used with Spark), [[delta-lake|Delta Lake]] (ACID + time travel on Spark), [[apache-avro|Avro]] (row-oriented, write-heavy, used with Kafka), **ORC** (columnar, ACID, indexes). Plus JSON/CSV.

## Connects to
- Entities: [[apache-parquet]], [[delta-lake]], [[apache-avro]], [[acid-transactions]], [[microservices]]
- Concepts: [[data-storage-and-formats]], [[distributed-systems-foundations]], [[cloud-native-architecture]]
- Related sources: [[distributed-data-systems]], [[cloud-native-applications]], [[apache-spark]]
