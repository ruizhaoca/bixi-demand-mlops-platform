# Source: Securing ML Applications

One-line: Security for ML systems — the OWASP Top 10 web risks, attacks specific to ML (poisoning, evasion, inversion, etc.), and defenses.

Raw: `../markdown/Securing ML Applications.md` (28 slides). Optional course topic.

## Key takeaways
- **[[owasp-top-10|OWASP Top 10]]** (web app risks): injection, broken authentication, sensitive data exposure, XXE, broken access control, security misconfiguration, XSS, insecure deserialization, known-vulnerable components, insufficient logging & monitoring.
- **[[adversarial-ml-attacks|Attacks against ML]]**:
  - **Poisoning** — inject adversarial data into training (e.g. Microsoft Tay).
  - **Evasion** — craft input to force misclassification (CV Dazzle, single-pixel attacks, stop-sign stickers).
  - **Impersonation** — fool a model into misidentifying (fingerprints, deepfakes).
  - **Inversion** — probe an API to extract a model's memorized private training data; differential privacy as a costly mitigation; GDPR implications.
  - Attacks against recommenders, fake reviews, Google bowling, click fraud — anything automated is attackable at scale.
- **Defenses**: security audits, RBAC + access-risk minimization, monitoring, penetration testing, **safety verification** (consistent output / sensitivity to small input changes), and **[[model-explainability|model explainability]]**.
- **Tools**: CleverHans, Foolbox.

## Connects to
- Entities: [[owasp-top-10]], [[adversarial-ml-attacks]]
- Concepts: [[responsible-ai]], [[ml-testing-and-monitoring]]
- Related sources: [[model-explainability]] (explainability as a defense), [[fairness-bias-ml]], [[data-drift]] (poisoning ≈ malicious drift)
