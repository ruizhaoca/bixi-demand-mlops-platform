# Entity: Lambda & Kappa Architectures

The two architectures that combine batch and stream — see [[batch-vs-stream-processing]].

- **Lambda**: hybrid with three layers — **batch layer** (master dataset, precomputed batch views, scheduled ETL), **speed/stream layer** (real-time views for recent data not yet in batch views), **serving layer** (indexes both for low-latency queries). New data feeds batch + speed simultaneously.
- **Kappa**: a simplification — Lambda with the batch layer removed. Everything flows through the streaming system; reprocessing = replaying the stream.

Appears in: [[batch-stream-processing]]
