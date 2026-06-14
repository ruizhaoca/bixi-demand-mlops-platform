# Entity: Bayesian Optimization

The informed approach to hyperparameter optimization — key method in [[automl-and-tuning]].

- Builds a **surrogate** probabilistic model mapping hyperparameters → expected objective score; uses it to pick the next, most-promising trial. Prior → posterior as trials accumulate ("become less wrong").
- Beats grid/random search because it's **informed by past evaluations** — fewer expensive objective calls. Related: TPE (Tree-structured Parzen Estimators).
- Frameworks: BayesianOptimization, HyperOpt (TPE), Optuna; integrates with [[mlflow|MLflow]].

Appears in: [[automl-fine-tuning]]
