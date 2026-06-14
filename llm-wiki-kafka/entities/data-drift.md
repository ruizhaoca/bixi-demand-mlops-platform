# Entity: Data Drift

The central runtime failure mode of deployed models — core to [[ml-testing-and-monitoring]].

- Drift = distribution change that degrades a model. **Types**: feature/covariate drift, data drift, **concept drift** (input→output relationship changes), dual/multi drift, prediction drift, target/label drift. Causes: real change, data-integrity/pipeline issues, seasonality.
- **Concept-drift remedies**: frequent retraining, weighting recent data, recency-aware splits, ensemble correction, time-series feature engineering.
- **Detection**: statistical — KL / JS divergence, KS test, L-infinity distance (Alibi-Detect `KSDrift`/`TabularDrift`); model-based classifier. [[tfdv|TFDV]] does drift + skew detection.
- Malicious drift = [[adversarial-ml-attacks|poisoning]] ([[securing-ml-applications]]).

Appears in: [[machine-learning-engineering]], [[real-world-ml-in-production]]
