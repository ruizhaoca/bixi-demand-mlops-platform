"""Model zoo, metrics, Optuna HPO and FLAML AutoML.

The training stage (``bixi.pipeline``) uses these building blocks to:
  1. score a naive baseline (predict the historical-average feature),
  2. train several candidate model families with sane defaults,
  3. run a FLAML AutoML search,
  4. run Optuna Bayesian HPO on the strongest family,
then select the best model by validation RMSE and evaluate it on the test split.

Targets are non-negative 15-minute demand counts (zero-inflated), so we expose
Poisson/Tweedie objectives alongside L2 and always clip predictions at 0.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_poisson_deviance,
    mean_squared_error,
    r2_score,
)

import lightgbm as lgb
import xgboost as xgb


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def clip_nonneg(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype="float64"), 0.0, None)


def metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype="float64")
    y_pred = clip_nonneg(y_pred)
    out = {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }
    try:  # poisson deviance needs strictly-positive predictions
        out["poisson_deviance"] = float(mean_poisson_deviance(y_true, y_pred + 1e-6))
    except Exception:
        out["poisson_deviance"] = float("nan")
    return out


# --------------------------------------------------------------------------- #
# Model zoo — name -> builder(**params) -> fitted-able estimator
# --------------------------------------------------------------------------- #
def _lgbm(objective: str, **overrides) -> lgb.LGBMRegressor:
    params = dict(
        objective=objective,
        n_estimators=600,
        learning_rate=0.05,
        num_leaves=128,
        min_child_samples=100,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        n_jobs=-1,
        verbosity=-1,
    )
    if objective == "tweedie":
        params["tweedie_variance_power"] = 1.2
    params.update(overrides)
    return lgb.LGBMRegressor(**params)


def _xgb(objective: str = "reg:squarederror", **overrides) -> xgb.XGBRegressor:
    params = dict(
        objective=objective,
        n_estimators=600,
        learning_rate=0.05,
        max_depth=8,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        tree_method="hist",
        n_jobs=-1,
        verbosity=0,
    )
    params.update(overrides)
    return xgb.XGBRegressor(**params)


def _hgb(loss: str = "squared_error", **overrides) -> HistGradientBoostingRegressor:
    params = dict(loss=loss, max_iter=500, learning_rate=0.05,
                  max_leaf_nodes=128, l2_regularization=1.0, random_state=42)
    params.update(overrides)
    return HistGradientBoostingRegressor(**params)


MODEL_ZOO: dict[str, Callable[..., Any]] = {
    "lgbm_l2": lambda **k: _lgbm("regression", **k),
    "lgbm_poisson": lambda **k: _lgbm("poisson", **k),
    "lgbm_tweedie": lambda **k: _lgbm("tweedie", **k),
    "xgb_l2": lambda **k: _xgb("reg:squarederror", **k),
    "hgb_poisson": lambda **k: _hgb("poisson", **k),
}

# Families that train fast enough to be the default candidate set.
DEFAULT_CANDIDATES = ["lgbm_l2", "lgbm_poisson", "lgbm_tweedie", "xgb_l2", "hgb_poisson"]


def fit_predict(name: str, X_tr, y_tr, X_eval, params: dict | None = None):
    model = MODEL_ZOO[name](**(params or {}))
    model.fit(X_tr, y_tr)
    return model, clip_nonneg(model.predict(X_eval))


# --------------------------------------------------------------------------- #
# Optuna Bayesian HPO (LightGBM family)
# --------------------------------------------------------------------------- #
def _subsample(X, y, n: int, seed: int = 42):
    """Random row subsample for fast HPO/AutoML search (final models refit on full)."""
    if n is None or len(X) <= n:
        return X, np.asarray(y)
    idx = np.random.default_rng(seed).choice(len(X), n, replace=False)
    Xs = X.iloc[idx] if hasattr(X, "iloc") else X[idx]
    return Xs, np.asarray(y)[idx]


def optuna_tune(
    X_tr, y_tr, X_val, y_val,
    *,
    objective: str = "regression",
    n_trials: int = 40,
    timeout: int | None = None,
    log_trial: Callable[[int, dict, float], None] | None = None,
    seed: int = 42,
    tune_sample: int | None = 2_000_000,
):
    """Tune a LightGBM model on a subsample (fast); return (best_params, best_rmse, study).

    The caller refits the chosen params on the FULL training data, so subsampling
    only speeds the search, not the final model.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    Xt, yt = _subsample(X_tr, y_tr, tune_sample, seed)

    def objective_fn(trial: "optuna.Trial") -> float:
        params = dict(
            n_estimators=trial.suggest_int("n_estimators", 300, 1500, step=100),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            num_leaves=trial.suggest_int("num_leaves", 31, 512, log=True),
            min_child_samples=trial.suggest_int("min_child_samples", 20, 400),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
            reg_lambda=trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            reg_alpha=trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        )
        model = _lgbm(objective, **params)
        model.fit(Xt, yt)
        rmse = metrics(y_val, model.predict(X_val))["rmse"]
        if log_trial:
            log_trial(trial.number, params, rmse)
        return rmse

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective_fn, n_trials=n_trials, timeout=timeout,
                   show_progress_bar=False)
    best = dict(study.best_params)
    best["objective"] = objective
    return best, float(study.best_value), study


# --------------------------------------------------------------------------- #
# FLAML AutoML
# --------------------------------------------------------------------------- #
def flaml_automl(X_tr, y_tr, X_val, y_val, *, time_budget: int = 120, seed: int = 42,
                 search_sample: int | None = 800_000):
    """Run FLAML AutoML; return (model, best_estimator_name, val_metrics).

    FLAML *searches* estimators/hyperparameters on a subsample (so it can try
    several models within the time budget even on tens of millions of rows), then
    we **refit the winning estimator on the full training data** via sklearn clone.
    Returns the raw fitted estimator (not the AutoML wrapper) so it serves cleanly
    and SHAP's fast TreeExplainer works.
    """
    from flaml import AutoML
    from sklearn.base import clone

    Xs, ys = _subsample(X_tr, y_tr, search_sample, seed)
    automl = AutoML()
    automl.fit(
        X_train=Xs, y_train=ys,
        X_val=X_val, y_val=np.asarray(y_val),
        task="regression", metric="rmse",
        estimator_list=["lgbm", "xgboost"],  # GBMs refit cheaply on full data
        time_budget=time_budget, seed=seed, verbose=0,
    )
    est = getattr(getattr(automl, "model", None), "estimator", None)
    if est is None:
        raise RuntimeError("FLAML returned no fitted estimator within the budget")
    try:                                  # refit winning config on the full data
        model = clone(est)
        model.fit(X_tr, y_tr)
    except Exception:
        model = est                       # fall back to the subsample-fit model
    val_m = metrics(y_val, model.predict(X_val))
    return model, str(automl.best_estimator), val_m
