# Concept: ML Testing & Monitoring

How you keep a deployed model trustworthy — testing before, monitoring after.

## The seven test types
Unit, **data tests** (schema), model validation (output ranges), model performance (statistical thresholds / A-B), integration, **data skew** tests, load tests. (From [[real-world-ml-in-production]].) Built on the general [[software-engineering-best-practices|testing discipline]].

## Monitoring in production: drift
The key runtime signal is **[[data-drift|drift]]** — distribution change that degrades the model. Types: feature, data, **concept** (target relationship), prediction, target/label drift.
- **Detection**: statistical (KL / **JS divergence**, **KS test**, **L-infinity distance**, via Alibi-Detect) and model-based (classifier separates reference vs. current).
- **[[tfdv|TFDV]]** does training-serving **skew** detection + drift detection in TFX.

## Security as a testing concern
**Safety verification** (consistent output, sensitivity to small input changes) and detecting [[adversarial-ml-attacks|poisoning]] (malicious drift) overlap with monitoring — see [[securing-ml-applications]].

## Connections
Closes the loop in [[mlops-lifecycle]]; drift → retraining; complements [[ml-deployment-and-serving]].

Sources: [[real-world-ml-in-production]], [[machine-learning-engineering]], [[securing-ml-applications]]
