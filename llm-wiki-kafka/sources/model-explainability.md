# Source: Model Explainability & Interpretability

One-line: Explainable AI (XAI) — the interpretability/explainability distinction, transparency levels, post-hoc and model-agnostic techniques, and the SHAP/LIME/ELI5 toolset.

Raw: `../markdown/Model Explainability and Interpretability.md` (28 slides). Based on Arrieta et al. (XAI survey) and Molnar's *Interpretable ML*.

## Key takeaways
- **Interpretability** = passive (how much a model makes sense to a human); **explainability** = active (procedures a model takes to clarify its function). Related nomenclature: understandability, comprehensibility, transparency.
- **Why XAI** (goals + audiences): trustworthiness, causality, transferability, informativeness, confidence, **fairness**, accessibility, interactivity, privacy awareness — for users, domain experts, managers, regulators.
- **Three model classes**: interpretable-by-design; transparent (simulatable / decomposable / algorithmically transparent); not-readily-interpretable → use **post-hoc** explainability.
- **Post-hoc techniques**: text, visual, local, by-example, by-simplification, feature-relevance explanations.
- **Model-agnostic methods**: PDP, ICE, ALE, feature interaction, permutation importance, global/local surrogate ([[lime|LIME]]), anchors, Shapley values, **[[shap|SHAP]]**.
- **Libraries**: ELI5 (debug classifiers; supports sklearn, Keras Grad-CAM, [[gradient-boosting|XGBoost/LightGBM/CatBoost]]), [[lime|LIME]], [[shap|SHAP]].

## Connects to
- Entities: [[shap]], [[lime]], [[gradient-boosting]]
- Concepts: [[responsible-ai]]
- Related sources: [[fairness-bias-ml]] (shares SHAP/LIME tooling), [[securing-ml-applications]] (explainability as a defense), [[automl-fine-tuning]]
