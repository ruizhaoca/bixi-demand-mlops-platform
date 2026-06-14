# Concept: AutoML & Hyperparameter Tuning

Automating the model-building pipeline — Module V.

## What AutoML automates
Data prep, feature engineering, algorithm selection, **hyperparameter optimization (HPO)**, deployment.

## HPO methods
- **Uninformed**: grid search, random search (ignore past trials).
- **Informed / surrogate-based**: [[bayesian-optimization|Bayesian optimization]], TPE — build a probabilistic surrogate of the objective, spend compute choosing the next trial to make fewer expensive evaluations.
- **Dedicated**: Hyperband, PBT, BOHB, Fabolas.
- Frameworks: HyperOpt (integrates with [[mlflow|MLflow]] + [[apache-spark|Spark]] trials), Optuna, Ray Tune, BayesianOptimization.

## Beyond HPO
- **NAS** (Neural Architecture Search): automate network design (search space + strategy + estimation; AdaNet, MorphNet).
- **AutoML frameworks**: Auto-SKLearn, TPOT, H2O.ai, AutoKeras, Databricks AutoML, Ludwig.
- **Fine-tuning [[gradient-boosting|gradient boosting]]** (XGBoost / LightGBM / CatBoost): learning rate, #trees, depth; manage under/overfitting.

## Connections
Feeds tuned models into [[mlops-lifecycle]] and [[ml-deployment-and-serving]]; tuned boosting models are later explained via [[model-explainability|SHAP/ELI5]].

Sources: [[automl-fine-tuning]], [[machine-learning-engineering]]
