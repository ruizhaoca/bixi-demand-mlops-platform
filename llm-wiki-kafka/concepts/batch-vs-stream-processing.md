# Concept: Batch vs. Stream Processing

The central data-processing dichotomy of Module I, and the conceptual home of the [[kafka-spark-assignment]].

## The core distinction
- **Batch / offline**: operates on **bounded** input (fixed, known size). Scheduled, throughput-optimized, no user waiting. Output derived from immutable input. (See [[batch-stream-processing]], [[hadoop-mapreduce]].)
- **Stream / near-real-time**: operates on **unbounded** events shortly after they occur. Lower latency than batch. (See [[apache-kafka]], [[ksqldb]].)
- **Online services** sit apart: request/response, availability- and latency-bound.

## How the tools line up
- Batch tooling evolved: [[hadoop-mapreduce|Unix tools → MapReduce/HDFS]] → data-flow/DAG engines ([[apache-spark|Spark]], Flink, Tez).
- Stream tooling: [[apache-kafka|Kafka]] transmits event streams; CDC (Debezium) turns DB changes into streams; [[ksqldb|ksqlDB]] processes them (push vs. pull queries; streams = append-only facts, tables = latest-per-key).
- [[apache-spark|Spark]] spans both (micro-batching + Spark Streaming); [[delta-lake|Delta Lake]] unifies batch + streaming over one table.

## Combining the two
[[lambda-kappa-architecture|Lambda]] runs batch + speed layers in parallel behind a serving layer; **Kappa** drops the batch layer and reprocesses through the stream.

## Why it recurs
The bounded/unbounded split echoes through storage ([[apache-parquet|Parquet]] read-heavy vs. [[apache-avro|Avro]] write-heavy — see [[data-storage-and-formats]]) and through ML ([[ml-deployment-and-serving|offline vs. real-time prediction]]).

Sources: [[batch-stream-processing]], [[apache-spark]], [[kafka-cheat-sheet]], [[syllabus]]
