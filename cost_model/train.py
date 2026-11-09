"""Train next-year cost models and log everything to MLflow.

    uv run python -m cost_model.train                 # all models
    uv run python -m cost_model.train gbm_full        # one model

Each model is one MLflow run in experiment "next-year-cost" with params, metrics for
two evaluation sets, calibration plots and the fitted sklearn pipeline:
  valid = 20% of beneficiaries held out from base year 2008 (same period: model quality)
  test  = base year 2009 -> 2010 (new period: model quality + drift)
The best model by valid RMSE is registered as "next_year_cost" with alias "champion".
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from cost_model.dataset import CHRONIC, OUT as DATASET

TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5050")
EXPERIMENT = "next-year-cost"
REGISTERED = "next_year_cost"
TARGET = "y_cost_next"
# skops (MLflow's default sklearn format) refuses unknown types on load. These are the
# internals of HistGradientBoosting; trusted because we only load models we trained.
SKOPS_TRUSTED = ["functools.partial", "sklearn.utils.validation.check_array",
                 "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]

DEMO = ["age", "sex", "race", "esrd", "state", "partd_months"]
CATEGORICAL = ["sex", "race", "state"]
COST_T = ["ip_cost", "op_cost", "car_cost", "rx_cost"]
UTIL_T = ["ip_stays", "ip_days", "op_claims", "car_claims", "rx_fills", "rx_distinct_ndc", "dx3_distinct"]


# ---------------------------------------------------------------- models
def linear_demo_chronic() -> Pipeline:
    """Actuarial-style baseline: additive cost per age band, sex, ESRD and chronic condition
    (the shape of CMS-HCC risk adjustment, without diagnosis groupers)."""
    pre = ColumnTransformer([
        ("onehot", OneHotEncoder(handle_unknown="ignore"), ["age_band", "sex"]),
        ("pass", "passthrough", ["esrd", *CHRONIC]),
    ])
    return Pipeline([("pre", pre), ("model", LinearRegression())])


def gbm(features: list[str]) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson",            # costs: non-negative, right-skewed, mean-calibrated
        learning_rate=0.08, max_iter=400, max_leaf_nodes=63, min_samples_leaf=200,
        l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
        n_iter_no_change=20, categorical_features=[f for f in features if f in CATEGORICAL],
        random_state=42,
    )


MODELS = {
    # name: (features, factory, description)
    "mean_baseline": (DEMO, lambda f: DummyRegressor(strategy="mean"),
                      "Predict the training mean for everyone. Anything useful must beat this."),
    "linear_demo_chronic": (["age_band", "sex", "esrd", *CHRONIC], lambda f: linear_demo_chronic(),
                            "Linear: age band + sex + ESRD + 11 chronic flags."),
    "gbm_demo_chronic": ([*DEMO, *CHRONIC, "n_chronic"], gbm,
                         "Gradient boosting on demographics + chronic flags (no prior cost)."),
    "gbm_full": ([*DEMO, *CHRONIC, "n_chronic", *COST_T, *UTIL_T], gbm,
                 "Gradient boosting on demographics + chronic + prior-year cost & utilization."),
}


# ---------------------------------------------------------------- data
def load() -> dict[str, pd.DataFrame]:
    df = pd.read_parquet(DATASET)
    for c in df.select_dtypes("object").columns.difference(["desynpuf_id", "split"]):
        df[c] = df[c].astype(float)
    for c in df.columns:
        if str(df[c].dtype).startswith(("decimal", "Decimal")) or df[c].dtype == object and c not in ("desynpuf_id", "split"):
            df[c] = pd.to_numeric(df[c])
    df[TARGET] = df[TARGET].astype(float).clip(lower=0)       # a handful of negative adjustments
    df["age_band"] = pd.cut(df["age"], [0, 64, 69, 74, 79, 84, 200],
                            labels=["<65", "65-69", "70-74", "75-79", "80-84", "85+"]).astype(str)
    # deterministic 80/20 beneficiary split of the 2008 base year
    bucket = df["desynpuf_id"].map(lambda s: int(hashlib.md5(s.encode()).hexdigest()[:8], 16) % 10)
    is_2008 = df["split"] == "train"
    return {"train": df[is_2008 & (bucket >= 2)], "valid": df[is_2008 & (bucket < 2)],
            "test": df[df["split"] == "test"]}


# ---------------------------------------------------------------- metrics
def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    order = np.argsort(-p)
    top = order[: len(order) // 10]
    # normalized Gini: how well the ranking concentrates actual cost (1 = perfect, 0 = random)
    def gini(actual, pred):
        o = np.argsort(-pred)
        cum = np.cumsum(actual[o]) / actual.sum()
        return (cum.sum() / len(actual)) - (len(actual) + 1) / (2 * len(actual))
    return {
        "mae": mean_absolute_error(y, p),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "r2": r2_score(y, p),
        "predictive_ratio": p.sum() / y.sum(),           # 1.0 = total dollars right
        "top10_capture": y[top].sum() / y.sum(),         # share of next-year cost in predicted top 10%
        "gini_norm": gini(y, p) / gini(y, y),
    }


def calibration_plot(y: np.ndarray, p: np.ndarray, title: str, path: Path) -> None:
    dec = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
    g = pd.DataFrame({"y": y, "p": p, "d": dec}).groupby("d").mean()
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(1, 11)
    ax.bar(x - 0.2, g["p"], 0.4, label="predicted")
    ax.bar(x + 0.2, g["y"], 0.4, label="actual")
    ax.set_xlabel("decile of predicted cost"); ax.set_ylabel("mean next-year cost ($)")
    ax.set_title(title); ax.set_xticks(x); ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)


def importance_plot(model, X: pd.DataFrame, y: np.ndarray, path: Path) -> pd.Series:
    r = permutation_importance(model, X, y, n_repeats=3, random_state=0, scoring="r2", n_jobs=1)
    imp = pd.Series(r.importances_mean, index=X.columns).sort_values()
    fig, ax = plt.subplots(figsize=(6, max(3, 0.25 * len(imp))))
    imp.plot.barh(ax=ax); ax.set_xlabel("drop in R² when shuffled (valid sample)")
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
    return imp


# ---------------------------------------------------------------- run
def run(name: str, data: dict[str, pd.DataFrame]) -> tuple[str, float]:
    features, factory, desc = MODELS[name]
    tr, va, te = data["train"], data["valid"], data["test"]
    with mlflow.start_run(run_name=name, description=desc) as r:
        mlflow.set_tags({"target": TARGET, "train_period": "2008->2009", "dataset": str(DATASET)})
        model = factory(features)
        params = {"model": name, "n_features": len(features), "features": ",".join(features),
                  "train_rows": len(tr), "valid_rows": len(va), "test_rows": len(te)}
        if isinstance(model, HistGradientBoostingRegressor):
            params.update({k: v for k, v in model.get_params().items()
                           if k in ("loss", "learning_rate", "max_iter", "max_leaf_nodes",
                                    "min_samples_leaf", "l2_regularization")})
        mlflow.log_params(params)

        t0 = time.time()
        model.fit(tr[features], tr[TARGET])
        mlflow.log_metric("fit_seconds", time.time() - t0)
        if hasattr(model, "n_iter_"):
            mlflow.log_metric("n_iter", model.n_iter_)

        with tempfile.TemporaryDirectory() as tmp:
            for split, d in (("valid", va), ("test", te)):
                p = np.asarray(model.predict(d[features]), dtype=float)
                y = d[TARGET].to_numpy()
                mlflow.log_metrics({f"{split}_{k}": v for k, v in metrics(y, p).items()})
                f = Path(tmp) / f"calibration_{split}.png"
                calibration_plot(y, p, f"{name} — {split}", f)
                mlflow.log_artifact(str(f), "plots")
            if name.startswith("gbm"):
                s = va.sample(30_000, random_state=0)
                f = Path(tmp) / "permutation_importance.png"
                imp = importance_plot(model, s[features], s[TARGET].to_numpy(), f)
                mlflow.log_artifact(str(f), "plots")
                mlflow.log_dict(imp.sort_values(ascending=False).round(5).to_dict(), "feature_importance.json")

        example = va[features].head(5)
        mlflow.sklearn.log_model(model, name="model", input_example=example,
                                 signature=infer_signature(example, model.predict(example)),
                                 skops_trusted_types=SKOPS_TRUSTED)
        rmse = mlflow.get_run(r.info.run_id).data.metrics["valid_rmse"]
        m = mlflow.get_run(r.info.run_id).data.metrics
        print(f"{name:22s} valid: R²={m['valid_r2']:.3f} RMSE={m['valid_rmse']:>7,.0f} "
              f"gini={m['valid_gini_norm']:.3f} top10={m['valid_top10_capture']:.2f} PR={m['valid_predictive_ratio']:.2f} | "
              f"test: R²={m['test_r2']:.3f} gini={m['test_gini_norm']:.3f} PR={m['test_predictive_ratio']:.2f} "
              f"({m['fit_seconds']:.0f}s)", flush=True)
        return r.info.run_id, rmse


def main() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT)
    names = sys.argv[1:] or list(MODELS)
    data = load()
    print({k: len(v) for k, v in data.items()})
    results = {n: run(n, data) for n in names}
    best = min(results, key=lambda n: results[n][1])
    mv = mlflow.register_model(f"runs:/{results[best][0]}/model", REGISTERED)
    client = mlflow.MlflowClient()
    current = None
    try:
        current = client.get_model_version_by_alias(REGISTERED, "champion")
    except mlflow.exceptions.MlflowException:
        pass
    cur_rmse = mlflow.get_run(current.run_id).data.metrics["valid_rmse"] if current else float("inf")
    if results[best][1] < cur_rmse:
        client.set_registered_model_alias(REGISTERED, "champion", mv.version)
        print(f"champion -> {REGISTERED} v{mv.version} ({best})")
    else:
        print(f"registered {REGISTERED} v{mv.version} ({best}); champion unchanged (v{current.version} is better)")


if __name__ == "__main__":
    main()
