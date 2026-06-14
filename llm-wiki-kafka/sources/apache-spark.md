# Source: Apache Spark — An Intro

One-line: Intro lecture on [[apache-spark|Apache Spark]] as a unified analytics engine — its cluster model, core APIs, and DataFrame usage.

Raw: `../markdown/ApacheSpark.md`

## Key takeaways
- Spark is a **unified analytics engine** for big data with built-in modules for streaming, SQL, ML, and graph processing. Originated at UC Berkeley (2009). APIs in Scala, Python, Java, SQL, R. Uses **micro-batching**.
- Use Spark to **scale out** (data/model too big for one machine) or **speed up** (faster results).
- Cluster = **one driver + many executor JVMs**.
- Three APIs: **RDD** (Resilient Distributed Dataset — fault-tolerant, distributed, immutable, tracks lineage, parallel ops), **DataFrame** (columnar, built on RDDs, optimized), **Dataset**.
- RDD ops split into **transformations** (filter, sample, union — lazy) and **actions** (count, take, collect — trigger execution).
- Performance from **Tungsten** and **Catalyst** optimizers; uniform APIs across languages.
- `SparkSession` creates DataFrames, registers tables, runs SQL, caches, reads Parquet. Reads JSON, [[apache-parquet|Parquet]], TXT.

## Connects to
- Entity: [[apache-spark]], [[apache-parquet]], [[databricks]]
- Concepts: [[batch-vs-stream-processing]], [[data-storage-and-formats]], [[distributed-systems-foundations]]
- Related sources: [[batch-stream-processing]] (Spark as a data-flow engine), [[kafka-spark-assignment]]
