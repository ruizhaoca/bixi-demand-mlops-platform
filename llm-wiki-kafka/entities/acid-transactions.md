# Entity: ACID Transactions

The transactional guarantee model — central to [[distributed-systems-foundations]] and [[data-storage-and-formats]].

- **Atomicity** (all-or-nothing), **Consistency** (valid state→valid state), **Isolation** (concurrent = serial effect), **Durability** (committed survives crashes).
- **Weak isolation levels** (used in practice): read committed (no dirty read/write), snapshot isolation / repeatable read (MVCC). Anomalies: dirty read/write, lost update, read skew, write skew, phantoms.
- **Serializability** techniques: actual serial execution, two-phase locking (2PL), serializable snapshot isolation (SSI).
- Contrast **BASE** ([[cap-theorem|AP / eventual consistency]]). [[delta-lake|Delta Lake]] and ORC bring ACID to data lakes.

Appears in: [[distributed-data-systems]], [[nosql-big-data-files]]
