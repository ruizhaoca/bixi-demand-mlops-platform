# Source: Apache Kafka — An Intro (Cheat Sheet)

One-line: A command reference for running [[apache-kafka|Kafka]] locally (landoop/fast-data-dev Docker image) and operating topics, producers, consumers, Avro messages, configs, ACLs, and ZooKeeper.

Raw: `../markdown/kafka-cheat-sheet.md` (28 slides).

## Key takeaways
- Run a local Kafka dev stack via the **landoop/fast-data-dev** [[docker|Docker]] image (exposes broker 9092, schema registry 8081, etc.).
- **Topics**: `kafka-topics --create/--list/--alter/--delete/--describe` with `--partitions` and `--replication-factor`. Can inspect under-replicated partitions.
- **Producers**: `kafka-console-producer`; produce from file; **`kafka-avro-console-producer`** with `value.schema` + `schema.registry.url` for [[apache-avro|Avro]] messages.
- **Consumers**: `kafka-console-consumer --from-beginning`; consumer groups (`group.id`); `kafka-avro-console-consumer` for Avro.
- **Config**: per-topic overrides (e.g. `retention.ms`). **Performance**: `kafka-producer-perf-test`. **ACLs**: producer/consumer permissions per principal. **ZooKeeper** shell for coordination.

## Connects to
- Entities: [[apache-kafka]], [[apache-avro]], [[docker]], [[consensus-algorithms]] (ZooKeeper)
- Concepts: [[batch-vs-stream-processing]], [[kafka-spark-assignment]]
- Related sources: [[batch-stream-processing]] (Confluent Cloud equivalent of these commands)
