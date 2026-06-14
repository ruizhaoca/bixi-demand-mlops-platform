# Source: AutoML & Fine-Tuning

One-line: Automating the ML pipeline — what AutoML covers, hyperparameter optimization (grid/random → Bayesian), frameworks, Neural Architecture Search, and fine-tuning gradient boosting (XGBoost/LightGBM/CatBoost).

Raw: `../markdown/AutoML_Fine-Tuning.md` (48 slides).

## Key takeaways
- **AutoML** automates data prep, feature engineering, algorithm selection, **hyperparameter optimization (HPO)**, and deployment.
- **HPO**: hyperparameters are set before training (vs. learned model parameters). Evaluating the objective is expensive (each trial = train + validate).
  - Methods: exhaustive (**grid/random search** — uninformed by past trials), surrogate-model (**[[bayesian-optimization|Bayesian optimization]]**, TPE — informed, fewer iterations), dedicated (Hyperband, PBT, BOHB, Fabolas).
  - Frameworks: BayesianOptimization, **HyperOpt** (+ MLflow/Spark trials), **Optuna**, Ray Tune, Sherpa, SigOpt, Ax.
- **AutoML frameworks**: Auto-SKLearn, TPOT, H2O.ai AutoML, AutoKeras, Databricks AutoML, Ludwig, etc.
- **NAS** (Neural Architecture Search): search space + strategy + performance estimation; methods include RL, evolutionary, hill-climbing; algorithms AdaNet, MorphNet.
- **Fine-tuning [[gradient-boosting|gradient boosting]]**: LightGBM (leaf-wise), XGBoost (level-wise), CatBoost (categorical-native, depth-wise); tune learning rate, #trees, depth; manage under/overfitting via regularization & pruning.

## Connects to
- Entities: [[bayesian-optimization]], [[gradient-boosting]], [[mlflow]]
- Concepts: [[automl-and-tuning]], [[mlops-lifecycle]]
- Related sources: [[machine-learning-engineering]], [[model-explainability]] (boosting models are explained with SHAP/ELI5)
