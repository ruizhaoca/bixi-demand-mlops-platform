# Entity: TFDV (TensorFlow Data Validation)

A data-validation tool used in TFX pipelines — part of [[ml-testing-and-monitoring]].

- Visualizes feature-value distributions (Facets) to catch data problems.
- **Training-serving skew detection**: flags when training feature distributions differ significantly from serving data (using L-infinity threshold).
- **Drift detection** between consecutive data spans: L-infinity distance for categorical features, approximate JS divergence for numeric. See [[data-drift]].

Appears in: [[machine-learning-engineering]]
