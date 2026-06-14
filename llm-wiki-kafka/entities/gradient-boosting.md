# Entity: Gradient Boosting (XGBoost / LightGBM / CatBoost)

The ensemble technique fine-tuned in [[automl-and-tuning]] and explained in [[model-explainability]].

- Builds models incrementally via boosting; high accuracy on tabular classification/regression.
- **XGBoost** — level-wise tree growth, precise/efficient. **LightGBM** — leaf-wise growth, fast on large data (risk of overfit on small). **CatBoost** — depth-wise, categorical-native (minimal preprocessing).
- Key tuning: learning rate, #trees, tree depth; manage under/overfitting (regularization, pruning). Tuned via [[bayesian-optimization]]/HyperOpt.
- Explained via ELI5 / [[shap|SHAP]] feature importances.

Appears in: [[automl-fine-tuning]], [[model-explainability]]
