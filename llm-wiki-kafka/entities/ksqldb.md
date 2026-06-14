# Entity: ksqlDB / KSQL

The event-streaming database for [[apache-kafka|Kafka]] — SQL over streams.

- Kafka-native, real-time, lightweight SQL syntax. Capture events (source connectors), transform continuously (`CREATE STREAM ... EMIT CHANGES`), build materialized views (`CREATE TABLE`).
- **Collections**: *streams* (immutable, append-only events — historical facts) vs. *tables* (mutable, latest-per-key).
- **Queries**: *push* (subscribe to results as they change — async flows) vs. *pull* (fetch current state of a materialized view — request/response).
- A concrete stream-processing tool for [[batch-vs-stream-processing]].

Appears in: [[batch-stream-processing]]
