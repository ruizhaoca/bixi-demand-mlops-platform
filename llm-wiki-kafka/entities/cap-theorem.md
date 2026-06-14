# Entity: CAP Theorem

The trade-off at the heart of [[distributed-systems-foundations]].

- Naive form: Consistency, Availability, Partition tolerance — "pick 2 of 3." But partitions are faults you don't choose, so the better framing is **Consistent *or* Available when Partitioned**.
- **CP** (enforced consistency) — consistency even during a partition, at the cost of availability; uses quorum/majority (Paxos). E.g. banking.
- **AP** (eventual consistency / **BASE**) — availability during a partition, converging later; a liveness (not safety) guarantee.
- Relates to replication choices and [[consensus-algorithms|consensus]].

Appears in: [[distributed-data-systems]]
