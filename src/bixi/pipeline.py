"""Resumable, staged BIXI modeling pipeline.

Stages: ingest -> features -> serving -> data -> train -> explain -> fairness ->
drift -> register. A default run rebuilds everything from public source data;
successful stages remain resumable through their S3 checkpoint markers.

Each stage writes its outputs + a ``_SUCCESS`` marker to
``s3://<PIPELINE_BUCKET>/<PIPELINE_PREFIX>/runs/<run_id>/<target>/<stage>/`` so a
run can be resumed from any step. The same code path runs locally on a subsample
(``--local-dir`` / ``--sample-stations``) and on AWS Batch over the full dataset.

Examples
--------
  # whole pipeline, both targets, full data (cloud / Batch)
  python -m bixi.pipeline --targets both --run-id 2024-prod

  # resume from training onward (reuses the data-stage checkpoint)
  python -m bixi.pipeline --targets both --run-id 2024-prod --from train

  # just re-run drift for departures
  python -m bixi.pipeline --targets departure --run-id 2024-prod --only drift --force

  # fast local smoke test on a station subsample
  python -m bixi.pipeline --from data --targets departure --run-id smoke \
      --local-dir ~/bixi_data --sample-stations 80 --n-trials 8 --flaml-budget 30
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import tempfile
import time

import numpy as np

from . import config, data, drift, explain, fairness, io, models, registry


# --------------------------------------------------------------------------- #
# Run context
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class Ctx:
    target: str
    run_id: str
    local_dir: str | None = None
    sample_stations: int | None = None
    sample_frac: float | None = None
    n_trials: int = 40
    flaml_budget: int = 120
    force: bool = False
    r2_alert: float = 0.55
    # in-memory state
    splits: dict | None = None          # split -> (X, y, meta)
    encoder: data.StationEncoder | None = None
    tiers: dict | None = None
    model=None
    mlflow_run_id: str | None = None
    baseline_r2: float | None = None

    def key(self, stage: str, name: str) -> str:
        return f"{config.stage_prefix(self.run_id, self.target, stage)}/{name}"


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _upload(local_path: str, ctx: Ctx, stage: str) -> str:
    return io.upload_file(local_path, ctx.key(stage, os.path.basename(local_path)))


# --------------------------------------------------------------------------- #
# Lazy loaders (make every stage runnable standalone on resume)
# --------------------------------------------------------------------------- #
def ensure_data(ctx: Ctx) -> None:
    if ctx.splits is not None:
        return
    # encoder + tiers: from the data-stage checkpoint if present, else fit now
    enc_key = ctx.key("data", "encoder.pkl")
    tier_key = ctx.key("data", "tiers.json")
    raw = {s: data.load_split(ctx.target, s, local_dir=ctx.local_dir,
                              sample_stations=ctx.sample_stations,
                              sample_frac=ctx.sample_frac)
           for s in ("train", "val", "test")}
    if io.exists(enc_key) and io.exists(tier_key) and not ctx.force:
        ctx.encoder = io.get_pickle(enc_key)
        ctx.tiers = io.get_json(tier_key)
    if ctx.encoder is None:
        ctx.encoder = data.StationEncoder().fit(raw["train"])
        ctx.tiers = data.fit_demand_tiers(raw["train"])
    ctx.splits = {s: data.prepare_xy(raw[s], ctx.encoder, ctx.tiers) for s in raw}


def ensure_model(ctx: Ctx) -> None:
    if ctx.model is not None:
        return
    ctx.model = io.get_pickle(ctx.key("train", "best_model.pkl"))
    try:
        meta = io.get_json(ctx.key("train", "metrics.json"))
        ctx.mlflow_run_id = meta.get("mlflow_run_id")
        ctx.baseline_r2 = meta.get("selected", {}).get("val", {}).get("r2")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def stage_ingest(ctx: Ctx) -> None:
    from . import ingest
    ingest.ensure_raw_in_s3(force=ctx.force)


def stage_features(ctx: Ctx) -> None:
    from . import feature_engineering
    written = feature_engineering.build_features_for_target(ctx.target, force=ctx.force)
    _log(f"[features] {ctx.target}: built/verified {len(written)} feature table(s)")


def stage_serving(ctx: Ctx) -> None:
    from . import serving_baselines

    uri = serving_baselines.generate_for_target(
        ctx.target,
        ctx.run_id,
        force=ctx.force,
    )
    _log(f"[serving] {ctx.target}: {uri}")


def stage_data(ctx: Ctx) -> None:
    ensure_data(ctx)
    (Xtr, ytr, _), (Xva, _, _), (Xte, _, _) = (
        ctx.splits["train"], ctx.splits["val"], ctx.splits["test"])
    io.put_pickle(ctx.key("data", "encoder.pkl"), ctx.encoder)
    io.put_json(ctx.key("data", "tiers.json"), ctx.tiers)
    summary = {"target": ctx.target,
               "n_features": Xtr.shape[1], "features": list(Xtr.columns),
               "rows": {"train": int(len(Xtr)), "val": int(len(Xva)), "test": int(len(Xte))},
               "target_mean_train": float(ytr.mean())}
    io.put_json(ctx.key("data", "data_summary.json"), summary)
    _log(f"[data] {ctx.target}: rows train={len(Xtr):,} val={len(Xva):,} test={len(Xte):,}")


def stage_train(ctx: Ctx) -> None:
    import mlflow

    ensure_data(ctx)
    (Xtr, ytr, _), (Xva, yva, _), (Xte, yte, _) = (
        ctx.splits["train"], ctx.splits["val"], ctx.splits["test"])

    registry.init_mlflow()
    registry.set_experiment(ctx.target)

    results = {}   # name -> (model, val_metrics)

    with mlflow.start_run(run_name=f"{ctx.target}-train-{ctx.run_id}") as parent:
        ctx.mlflow_run_id = parent.info.run_id
        mlflow.set_tags({"target": ctx.target, "run_id": ctx.run_id, "phase": "2-modeling"})
        mlflow.log_params({"n_train": len(Xtr), "n_val": len(Xva), "n_test": len(Xte),
                           "n_features": Xtr.shape[1]})

        # 0. Naive baseline = historical-average feature
        base_pred = Xva["hist_avg_demand"].to_numpy()
        base_m = models.metrics(yva, base_pred)
        registry.log_metrics("baseline_val", base_m)
        _log(f"[train] baseline(val) rmse={base_m['rmse']:.4f} r2={base_m['r2']:.4f}")

        # 1. Candidate model families
        for name in models.DEFAULT_CANDIDATES:
            with mlflow.start_run(run_name=name, nested=True):
                model, pred = models.fit_predict(name, Xtr, ytr, Xva)
                m = models.metrics(yva, pred)
                mlflow.log_param("model", name)
                registry.log_metrics("val", m)
                results[name] = (model, m)
                _log(f"[train] {name}(val) rmse={m['rmse']:.4f} r2={m['r2']:.4f}")

        # 2. FLAML AutoML
        try:
            with mlflow.start_run(run_name="flaml_automl", nested=True):
                automl, est, m = models.flaml_automl(Xtr, ytr, Xva, yva,
                                                     time_budget=ctx.flaml_budget)
                mlflow.log_param("flaml_best_estimator", est)
                registry.log_metrics("val", m)
                results["flaml"] = (automl, m)
                _log(f"[train] flaml({est})(val) rmse={m['rmse']:.4f} r2={m['r2']:.4f}")
        except Exception as e:
            _log(f"[train] FLAML skipped: {e}")

        # 3. Optuna HPO on LightGBM
        try:
            best_params, best_rmse, _ = models.optuna_tune(
                Xtr, ytr, Xva, yva, objective="regression",
                n_trials=ctx.n_trials,
                log_trial=lambda n, p, r: mlflow.log_metric("optuna_trial_rmse", r, step=n))
            tuned = models.MODEL_ZOO["lgbm_l2"](**{k: v for k, v in best_params.items()
                                                   if k != "objective"})
            tuned.fit(Xtr, ytr)
            m = models.metrics(yva, tuned.predict(Xva))
            mlflow.log_params({f"optuna_{k}": v for k, v in best_params.items()})
            registry.log_metrics("optuna_val", m)
            results["lgbm_optuna"] = (tuned, m)
            _log(f"[train] lgbm_optuna(val) rmse={m['rmse']:.4f} r2={m['r2']:.4f}")
        except Exception as e:
            _log(f"[train] Optuna skipped: {e}")

        # 4. Select best by validation RMSE, evaluate on test
        best_name = min(results, key=lambda k: results[k][1]["rmse"])
        best_model, best_val = results[best_name]
        test_m = models.metrics(yte, best_model.predict(Xte))
        ctx.model = best_model
        ctx.baseline_r2 = best_val["r2"]

        mlflow.set_tag("best_model", best_name)
        registry.log_metrics("best_val", best_val)
        registry.log_metrics("best_test", test_m)
        registry.log_model(best_model, name="model")
        _log(f"[train] SELECTED {best_name}: val rmse={best_val['rmse']:.4f} "
             f"r2={best_val['r2']:.4f} | test rmse={test_m['rmse']:.4f} r2={test_m['r2']:.4f}")

    # Persist checkpoint
    io.put_pickle(ctx.key("train", "best_model.pkl"), best_model)
    io.put_json(ctx.key("train", "metrics.json"), {
        "target": ctx.target, "run_id": ctx.run_id,
        "mlflow_run_id": ctx.mlflow_run_id, "best_model": best_name,
        "baseline_val": base_m,
        "candidates": {k: v[1] for k, v in results.items()},
        "selected": {"name": best_name, "val": best_val, "test": test_m},
    })


def stage_explain(ctx: Ctx) -> None:
    ensure_data(ctx)
    ensure_model(ctx)
    Xva = ctx.splits["val"][0]
    Xtr = ctx.splits["train"][0]
    with tempfile.TemporaryDirectory() as d:
        paths = explain.shap_artifacts(ctx.model, Xva, d)
        try:
            paths += explain.lime_artifacts(ctx.model, Xtr.sample(min(2000, len(Xtr)),
                                            random_state=0), Xva.head(3), d)
        except Exception as e:
            _log(f"[explain] LIME skipped: {e}")
        for p in paths:
            _upload(p, ctx, "explain")
    _log(f"[explain] {ctx.target}: {len(paths)} artifacts uploaded")


def stage_fairness(ctx: Ctx) -> None:
    ensure_data(ctx)
    ensure_model(ctx)
    Xte, yte, mte = ctx.splits["test"]
    pred = models.clip_nonneg(ctx.model.predict(Xte))
    report = fairness.fairness_report(mte, yte, pred)
    io.put_json(ctx.key("fairness", "fairness_report.json"), report)
    _log(f"[fairness] {ctx.target}: flags={report['flags']}")


def stage_drift(ctx: Ctx) -> None:
    ensure_data(ctx)
    ensure_model(ctx)
    Xtr, ytr, _ = ctx.splits["train"]
    ref_df = Xtr.copy(); ref_df[config.TARGET_COL] = np.asarray(ytr)
    ref_pred = models.clip_nonneg(ctx.model.predict(Xtr))
    with tempfile.TemporaryDirectory() as d:
        summaries = {}
        for split, period in (("val", "2025_may"), ("test", "2025_oct")):
            Xc, yc, _ = ctx.splits[split]
            cur_df = Xc.copy(); cur_df[config.TARGET_COL] = np.asarray(yc)
            cur_pred = models.clip_nonneg(ctx.model.predict(Xc))
            s = drift.analyze_period(ref_df, cur_df, ref_pred, cur_pred, period, d,
                                     r2_alert=ctx.r2_alert, ref_r2=ctx.baseline_r2)
            summaries[period] = s
        for f in os.listdir(d):
            _upload(os.path.join(d, f), ctx, "drift")
        io.put_json(ctx.key("drift", "drift_summary.json"), summaries)
    for p, s in summaries.items():
        _log(f"[drift] {ctx.target} {p}: feat_drifted={s['feature_drift']['n_drifted']}/"
             f"{s['feature_drift']['n_features']} target_drift={s['target_drift']['drift']} "
             f"concept_alert={s['concept_drift']['concept_drift_alert']}")


def stage_register(ctx: Ctx) -> None:
    if not ctx.mlflow_run_id:
        ensure_model(ctx)
    if not ctx.mlflow_run_id:
        _log("[register] no MLflow run id found; skipping registry promotion")
        return
    info = registry.register_production(ctx.mlflow_run_id, ctx.target)
    io.put_json(ctx.key("register", "registered_model.json"), info)
    _log(f"[register] {ctx.target}: {info}")


STAGE_FUNCS = {
    "ingest": stage_ingest, "features": stage_features,
    "serving": stage_serving,
    "data": stage_data, "train": stage_train,
    "explain": stage_explain, "fairness": stage_fairness,
    "drift": stage_drift, "register": stage_register,
}


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def resolve_stages(args) -> list[str]:
    if args.only:
        return [args.only]
    order = config.ALL_STAGES
    if args.from_stage:
        return order[order.index(args.from_stage):]
    if args.stages:
        req = [s.strip() for s in args.stages.split(",") if s.strip()]
        return req
    return config.DEFAULT_STAGES


def run_target(target: str, stages: list[str], args) -> None:
    ctx = Ctx(target=target, run_id=args.run_id, local_dir=args.local_dir,
              sample_stations=args.sample_stations, sample_frac=args.sample_frac,
              n_trials=args.n_trials, flaml_budget=args.flaml_budget,
              force=args.force, r2_alert=args.r2_alert)
    _log(f"=== target={target} stages={stages} run_id={args.run_id} ===")
    for stage in stages:
        if not args.force and io.has_success(ctx.run_id, target, stage):
            _log(f"[{stage}] already complete (skip; use --force to redo)")
            continue
        t0 = time.time()
        STAGE_FUNCS[stage](ctx)
        io.write_success(ctx.run_id, target, stage, {"seconds": round(time.time() - t0, 1)})
        _log(f"[{stage}] done in {time.time() - t0:.1f}s")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="BIXI demand modeling pipeline")
    ap.add_argument("--targets", default="both",
                    help="departure | arrival | both (default both)")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--stages", help="comma list, e.g. data,train,drift")
    ap.add_argument("--from", dest="from_stage", choices=config.ALL_STAGES,
                    help="run this stage through the end")
    ap.add_argument("--only", choices=config.ALL_STAGES, help="run exactly one stage")
    ap.add_argument("--local-dir", help="dir with local parquet (dev)")
    ap.add_argument("--sample-stations", type=int)
    ap.add_argument("--sample-frac", type=float)
    ap.add_argument("--n-trials", type=int, default=40)
    ap.add_argument("--flaml-budget", type=int, default=120)
    ap.add_argument("--r2-alert", type=float, default=0.55)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    targets = config.TARGETS if args.targets == "both" else (args.targets,)
    stages = resolve_stages(args)
    for target in targets:
        run_target(target, stages, args)


if __name__ == "__main__":
    main()
