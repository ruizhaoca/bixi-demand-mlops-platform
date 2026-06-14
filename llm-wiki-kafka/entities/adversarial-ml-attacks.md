# Entity: Adversarial ML Attacks

Attacks targeting ML models specifically — the ML-security half of [[securing-ml-applications]] and part of [[responsible-ai]].

- **Poisoning** — inject bad data into training (e.g. Microsoft Tay); any continually-retraining system is vulnerable — i.e. malicious [[data-drift]].
- **Evasion** — craft input to force misclassification (single-pixel, stop-sign stickers, CV Dazzle).
- **Impersonation** — fool a model into misidentifying (fingerprints, deepfakes).
- **Inversion** — probe an API to extract memorized private training data; differential privacy as a costly defense (GDPR implications).
- Recommender attacks, fake reviews, Google bowling, click fraud — automation enables attack at scale.
- **Defenses**: audits, RBAC, monitoring, penetration testing, safety verification, [[model-explainability|explainability]]. Tools: CleverHans, Foolbox.

Appears in: [[securing-ml-applications]]
