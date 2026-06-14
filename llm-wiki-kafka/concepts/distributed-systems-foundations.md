# Concept: Distributed Systems Foundations

The theory that makes the data tools reliable and scalable — the substrate under [[apache-kafka|Kafka]], [[apache-spark|Spark]], [[hadoop-mapreduce|HDFS]], and NoSQL.

## Why distribute
Scalability, fault tolerance / high availability, and latency. Achieved by moving from shared-memory (vertical) to **shared-nothing** (horizontal) scaling.

## Two primitives
- **Replication** — copies on multiple nodes (single-leader, multi-leader, leaderless/Dynamo-style). Gives redundancy + read scaling.
- **Partitioning** — splitting data into subsets (sharding / vertical / functional). Gives write scaling.

These two reappear directly in [[data-storage-and-formats|NoSQL scalability]] and in [[apache-kafka|Kafka's]] partitions/replication.

## Correctness under concurrency & faults
- **[[acid-transactions|ACID]]** + weak isolation levels (read committed, snapshot isolation/MVCC) and their anomalies (dirty read/write, lost update, read/write skew, phantoms); serializability via serial execution, 2PL, or SSI.
- **System models**: timing (sync / partially-sync / async) and faults (crash-stop / crash-recovery / Byzantine).
- **[[cap-theorem|CAP]]**: Consistent *or* Available when Partitioned. CP = enforced consistency; AP = eventual consistency / BASE.
- **Consistency & consensus**: linearizability vs. serializability; total order broadcast; [[consensus-algorithms|ZAB / Raft / Paxos]] (ZooKeeper, etcd) — the same ZooKeeper that coordinates [[apache-kafka|Kafka]].

Sources: [[distributed-data-systems]], [[nosql-big-data-files]], [[batch-stream-processing]]
