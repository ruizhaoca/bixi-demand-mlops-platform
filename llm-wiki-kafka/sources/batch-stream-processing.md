# Source: Batch & Stream Processing

One-line: The anchor lecture on processing data offline (batch) vs. near-real-time (stream), the architectures that combine them, and the tooling from Unix pipes to Kafka/ksqlDB.

Raw: `../markdown/BatchStreamProcessing.md` (72 slides). Based on Kleppmann, *Designing Data-Intensive Applications*, ch. 10–11.

## Key takeaways
- ML systems run at different frequencies — real-time, every minute, daily, weekly — driving three system types: **online services** (request/response, latency-bound), **batch/offline** (bounded input, throughput-bound, scheduled), and **stream/near-real-time** (operates on events shortly after they occur, lower latency than batch).
- Services should be stateless, autonomous, reusable black boxes ([[twelve-factor-app|12-Factor]]).
- **Batch architectures**: [[hadoop-mapreduce|Unix tools → Hadoop MapReduce/HDFS]] → data-flow engines ([[apache-spark|Spark]], Tez, Flink) which model a whole workflow as a DAG and keep more in memory. MapReduce join algorithms: sort-merge, broadcast hash, partitioned hash.
- **Combined architectures**: [[lambda-kappa-architecture|Lambda]] (batch + speed + serving layers) and **Kappa** (stream-only simplification).
- **Stream processing**: transmit events via [[apache-kafka|Kafka]]; capture DB changes via **CDC** (Debezium); process with [[ksqldb|KSQL/ksqlDB]] (push vs. pull queries, streams vs. tables).
- Includes hands-on [[confluent-cloud|Confluent Cloud]] CLI steps (create cluster, topic, API key, produce/consume) — directly feeds [[kafka-spark-assignment]].

## Connects to
- Entities: [[apache-kafka]], [[apache-spark]], [[hadoop-mapreduce]], [[ksqldb]], [[confluent-cloud]], [[lambda-kappa-architecture]]
- Concepts: [[batch-vs-stream-processing]], [[distributed-systems-foundations]], [[kafka-spark-assignment]]
- Related sources: [[apache-spark]], [[kafka-cheat-sheet]], [[distributed-data-systems]]
