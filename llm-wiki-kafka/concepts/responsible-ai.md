# Concept: Responsible AI

The "should we trust this model?" cluster — Module VI + the optional security topic. Three intertwined questions.

## 1. Can we understand it? — [[model-explainability|Explainability]]
Interpretability (passive) vs. explainability (active). Transparent-by-design vs. post-hoc, model-agnostic techniques (PDP, permutation importance, surrogates, Shapley). Tools: [[shap|SHAP]], [[lime|LIME]], ELI5.

## 2. Is it fair? — [[fairness-bias-ml|Fairness & Bias]]
Bias enters via data and algorithms (historical, representation, measurement, sampling, algorithmic…). Discrimination types (direct/indirect/systemic). Fairness notions (individual/group/subgroup). Interventions: pre- / in- / post-processing.

## 3. Is it secure? — [[securing-ml-applications|Security]]
[[owasp-top-10|OWASP Top 10]] web risks + [[adversarial-ml-attacks|ML-specific attacks]] (poisoning, evasion, impersonation, inversion). Defenses: audits, RBAC, monitoring, safety verification.

## The shared thread
All three converge on **trust** and share tooling: **explainability is a fairness goal *and* a security defense** ([[shap|SHAP]]/[[lime|LIME]] appear in all three decks). Fairness evaluation needs per-group metrics; security needs [[ml-testing-and-monitoring|monitoring]]; poisoning is malicious [[data-drift|drift]]. Together they are the governance layer over [[mlops-lifecycle]].

Sources: [[model-explainability]], [[fairness-bias-ml]], [[securing-ml-applications]], [[syllabus]]
