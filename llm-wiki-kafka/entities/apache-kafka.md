# Entity: Apache Kafka

A distributed event-streaming platform — the backbone of [[batch-vs-stream-processing|stream processing]] in this course and the producer side of the [[kafka-spark-assignment]].

- Transmits **event streams**: producers write to **topics** (partitioned, replicated); consumers read via consumer groups. Messages often serialized as [[apache-avro|Avro]] against a schema registry.
- Coordinated by ZooKeeper ([[consensus-algorithms]]); partitions/replication are the [[distributed-systems-foundations]] primitives in action.
- Run locally via the landoop/fast-data-dev [[docker|Docker]] image ([[kafka-cheat-sheet]]) or managed on [[confluent-cloud|Confluent Cloud]].
- Pairs with [[ksqldb|ksqlDB]] for stream processing and feeds [[apache-spark|Spark]] Structured Streaming.

Appears in: [[batch-stream-processing]], [[kafka-cheat-sheet]], [[cloud-native-applications]], [[syllabus]], [[nosql-big-data-files]]
