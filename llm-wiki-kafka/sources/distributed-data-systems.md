# Source: Distributed Data Systems

One-line: The theory lecture on why and how data is distributed — scalability, replication, partitioning, transactions/isolation, system models, the [[cap-theorem|CAP theorem]], and consistency/consensus.

Raw: `../markdown/Distributed Data Systems.md` (86 slides). Based on Kleppmann, ch. 5, 6, 7, 9.

## Key takeaways
- **Why distribute**: scalability, fault tolerance / high availability, latency.
- **Scaling**: shared-memory (vertical) → shared-disk → **shared-nothing** (horizontal). Two distribution methods: **replication** (copies) and **partitioning** (subsets).
- **Replication** models: single-leader (master/slave), multi-leader (active/active), leaderless (Dynamo-style: Riak, Cassandra, Voldemort).
- **Partitioning**: horizontal (sharding), vertical, functional.
- **Transactions**: [[acid-transactions|ACID]]; weak isolation levels (read committed, snapshot isolation/MVCC, lost-update & write-skew/phantom anomalies); serializability via serial execution, 2PL, or SSI.
- **System models**: synchronous / partially synchronous / asynchronous timing; crash-stop / crash-recovery / Byzantine faults. Real systems ≈ partially synchronous + crash-recovery.
- **[[cap-theorem|CAP]]**: better stated as "Consistent *or* Available when Partitioned." CP = enforced consistency (Paxos); AP = eventual consistency / BASE.
- **Consistency & consensus**: client-centric levels (RYW, monotonic reads/writes, WFR); **linearizability** (vs. serializability); total order broadcast; [[consensus-algorithms|consensus algorithms]] (ZAB/ZooKeeper, Raft/etcd, Paxos).

## Connects to
- Entities: [[cap-theorem]], [[acid-transactions]], [[consensus-algorithms]]
- Concepts: [[distributed-systems-foundations]], [[data-storage-and-formats]]
- Related sources: [[batch-stream-processing]], [[nosql-big-data-files]]
