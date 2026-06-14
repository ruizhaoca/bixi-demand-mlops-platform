# Source: Fairness & Bias in ML

One-line: A taxonomy of bias in ML — where bias enters, protected attributes, the many named bias types, kinds of discrimination, fairness definitions, and algorithmic fairness interventions.

Raw: `../markdown/Fairness and Bias in Machine Learning.md` (30 slides). Based on Mehrabi et al. survey + Barocas/Hardt/Narayanan.

## Key takeaways
- Models trained on **biased data** produce unfair, inaccurate predictions. Bias-related/protected attributes: race, color, religion, sex, age, marital/familial status, disability, location, income source, etc.
- **Evaluate per-group**, not just aggregate — overall metrics hide stark per-group gaps.
- **Impacted industries**: banking/credit (Equal Credit Opportunity Act), insurance, employment, housing, fraud, government, education, finance.
- **Types of bias** (many): historical, representation, measurement, evaluation, aggregation, population (Simpson's paradox), sampling, behavioral, popularity, **algorithmic** (added purely by the algorithm), presentation/ranking, emergent, self-selection, omitted-variable, observer, funding.
- **Discrimination**: direct, indirect, systemic, statistical, explainable vs. unexplainable (illegal).
- **Fairness**: individual (similar→similar), group (treat groups equally), subgroup.
- **Algorithmic fairness interventions**: **pre-processing** (transform data), **in-processing** (modify learning/objective), **post-processing** (reassign black-box labels via holdout).
- **Tools**: LIME, SHAP, ELI5, FairML, Google What-If, IBM bias toolkit.

## Connects to
- Entities: [[shap]], [[lime]]
- Concepts: [[responsible-ai]]
- Related sources: [[model-explainability]] (fairness is an XAI goal; shared tooling), [[securing-ml-applications]]
