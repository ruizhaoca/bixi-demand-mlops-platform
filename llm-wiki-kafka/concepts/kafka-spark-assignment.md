# Concept / Project: Kafka–Spark Assignment (Individual Assignment 1)

The course's first hands-on artifact and a concrete instance of [[batch-vs-stream-processing|Module I]]. Worth 15% ([[syllabus]]).

## The task
Generate an **event stream in [[apache-kafka|Kafka]]** ([[confluent-cloud|Confluent Cloud]]) and **process it in [[apache-spark|Spark]]** ([[databricks|Databricks]]).

Required steps (from `../instructions.md`):
- **Kafka/Confluent**: create a Confluent Cloud account → cluster → topic → schema.
- **Spark/Databricks**: create a Databricks Community Edition account → cluster → install the Confluent library via PyPi (pip) → configure the provided code → create a new **[[apache-avro|Avro]]** schema → produce events to the topic → process **batch** and **streaming**.

## Provided files
`../Kafka-spark-2022.dbc`, `../Kafka-spark-2022.ipynb`, `../Kafka-spark-2022.html` (the notebook in three formats).

## Concepts it exercises
- [[batch-vs-stream-processing]] — the assignment literally does both batch and streaming consumption.
- [[apache-avro]] — the event schema (row-oriented, write-heavy, Kafka-native — see [[data-storage-and-formats]]).
- [[apache-kafka]] topics/partitions; producer/consumer model ([[kafka-cheat-sheet]] is the local-CLI analogue).
- [[apache-spark]] DataFrames + Structured Streaming on [[databricks]].

## Connections
The theory lives in [[batch-stream-processing]]; the broader course frame in [[overview]] and [[syllabus]].
