# Entity: Consensus Algorithms

How distributed nodes agree on a value/order — the strong-consistency machinery of [[distributed-systems-foundations]].

- **Consensus requirements**: agreement, integrity, termination; tolerant of faulty processes via majority voting.
- **Total order broadcast** (reliable + totally-ordered delivery) is equivalent to consensus.
- Algorithms: **ZAB** (ZooKeeper Atomic Broadcast), **Raft** (etcd, RethinkDB), **Paxos** (Google Chubby, Spanner, Cassandra LWT).
- **ZooKeeper** (ZAB) provides linearizable coordination — and coordinates [[apache-kafka|Kafka]]. Enables linearizable systems ([[cap-theorem|CP]]).

Appears in: [[distributed-data-systems]], [[kafka-cheat-sheet]]
