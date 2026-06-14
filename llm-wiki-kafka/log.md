# Log

Append-only. Newest at the bottom. Grep with `grep "^## \[" log.md`.

## [2026-05-29] ingest | Initial batch ingest of all 14 course sources

Built the wiki from scratch over the full INSY 695 corpus.

- Read all 14 `../markdown/*.md` source files.
- Wrote 14 source summary pages under `sources/`.
- Created 10 concept pages under `concepts/`: [[batch-vs-stream-processing]], [[distributed-systems-foundations]], [[data-storage-and-formats]], [[cloud-native-architecture]], [[mlops-lifecycle]], [[ml-deployment-and-serving]], [[ml-testing-and-monitoring]], [[automl-and-tuning]], [[responsible-ai]], [[kafka-spark-assignment]].
- Created 26 entity pages under `entities/`: [[apache-kafka]], [[apache-spark]], [[confluent-cloud]], [[databricks]], [[apache-avro]], [[apache-parquet]], [[delta-lake]], [[hadoop-mapreduce]], [[kubernetes]], [[docker]], [[mlflow]], [[ksqldb]], [[cap-theorem]], [[acid-transactions]], [[consensus-algorithms]], [[lambda-kappa-architecture]], [[microservices]], [[twelve-factor-app]], [[gradient-boosting]], [[bayesian-optimization]], [[shap]], [[lime]], [[tfdv]], [[data-drift]], [[owasp-top-10]], [[adversarial-ml-attacks]].
- Wrote [[overview]] (course synthesis) and [[index]] (catalog).

Note: sources are slide decks, so source pages reconstruct prose from terse bullets. No contradictions found across sources on first pass; see [[index]] for lint candidates.
