# Entity: Apache Avro

A row-oriented data serialization system — the event format for the [[kafka-spark-assignment]].

- **Schema-based** (schemas defined in JSON); the schema travels with the data, enabling compact untagged serialization and schema evolution (resolve old vs. new schemas by field name).
- **Row-oriented, write-heavy** → used with [[apache-kafka|Kafka]] (contrast [[apache-parquet|Parquet]], columnar/read-heavy — see [[data-storage-and-formats]]).
- Used via `kafka-avro-console-producer/consumer` + schema registry ([[kafka-cheat-sheet]]).

Appears in: [[nosql-big-data-files]], [[kafka-cheat-sheet]], [[batch-stream-processing]], [[kafka-spark-assignment]]
