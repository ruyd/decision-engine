"""Loads the champion models from MLflow and explains their predictions with SHAP.

- next_year_cost@champion : member's expected cost next year (dollars) -> risk tier.
  Explained with SHAP's permutation explainer so contributions are in dollars and add up
  exactly to the prediction (base value + contributions = predicted cost).
- claim_fraud@champion    : Isolation Forest anomaly model over claim features.
  Explained with SHAP's tree explainer; sign flipped so positive = pushes toward "suspicious".
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass

import mlflow
import numpy as np
import pandas as pd
import shap

from engine import db
from engine.codes import COST_FEATURE_LABELS
from engine.config import MLFLOW_URI, MLFLOW_UI, REF
from fraud_model.features import FEATURES as FRAUD_FEATURES, LABELS as FRAUD_LABELS

log = logging.getLogger("engine.models")
TIERS = [(95, "Very high"), (80, "High"), (50, "Moderate"), (0, "Low")]


@dataclass
class ModelInfo:
    name: str
    version: str
    run_id: str
    metrics: dict
    params: dict
    loaded_at: float

    def card(self) -> dict:
        return {"name": self.name, "version": self.version, "run_id": self.run_id,
                "metrics": self.metrics, "params": self.params,
                "mlflow_url": f"{MLFLOW_UI}/#/models/{self.name}/versions/{self.version}",
                "run_url": f"{MLFLOW_UI}/#/experiments/0/runs/{self.run_id}"}


class Models:
    def __init__(self) -> None:
        mlflow.set_tracking_uri(MLFLOW_URI)
        self.client = mlflow.MlflowClient()
        self.cost_info = self._info("next_year_cost")
        self.cost = mlflow.sklearn.load_model("models:/next_year_cost@champion")
        self.cost_features = list(self.cost.feature_names_in_)
        snap = pd.read_parquet(REF / "member_snapshot.parquet")
        bg = snap[self.cost_features].astype(float).sample(300, random_state=0)
        self.cost_explainer = shap.PermutationExplainer(
            self.cost.predict, shap.maskers.Independent(bg, max_samples=300))
        self._snapshot = snap

        self.fraud_info = self._info("claim_fraud")
        self.fraud = mlflow.sklearn.load_model("models:/claim_fraud@champion")
        q = mlflow.artifacts.load_dict(f"runs:/{self.fraud_info.run_id}/score_quantiles.json")["quantiles"]
        self.fraud_q = np.asarray(q)
        self.fraud_explainer = shap.TreeExplainer(self.fraud)

    def _info(self, name: str) -> ModelInfo:
        mv = self.client.get_model_version_by_alias(name, "champion")
        run = self.client.get_run(mv.run_id)
        return ModelInfo(name, mv.version, mv.run_id, run.data.metrics, run.data.params, time.time())

    def versions(self) -> dict:
        return {"next_year_cost": self.cost_info.version, "claim_fraud": self.fraud_info.version}

    # ---------------------------------------------------------------- cost model
    def ensure_member_risk(self) -> None:
        """Score every member once per champion version (fast: ~1s predict + COPD into PG)."""
        row = db.q1("SELECT model_version, count(*) AS n FROM member_risk GROUP BY 1 LIMIT 1")
        if row and row["model_version"] == self.cost_info.version and row["n"] == len(self._snapshot):
            return
        t0 = time.time()
        X = self._snapshot[self.cost_features].astype(float)
        pred = np.clip(self.cost.predict(X), 0, None)
        pct = pd.Series(pred).rank(pct=True).to_numpy() * 100
        tier = np.select([pct >= 95, pct >= 80, pct >= 50], ["Very high", "High", "Moderate"], "Low")
        buf = io.StringIO()
        pd.DataFrame({"member_id": self._snapshot["member_id"], "predicted_cost": pred.round(2),
                      "risk_pct": pct.round(2), "risk_tier": tier, "model_version": self.cost_info.version}
                     ).to_csv(buf, index=False, header=False)
        with db.conn() as c:
            c.execute("TRUNCATE member_risk")
            with c.cursor().copy("COPY member_risk FROM STDIN WITH (FORMAT csv)") as cp:
                cp.write(buf.getvalue())
        log.info("scored %d members with next_year_cost v%s in %.1fs", len(pred), self.cost_info.version, time.time() - t0)

    def explain_cost(self, member_row: dict) -> dict:
        X = pd.DataFrame([{f: float(member_row.get(f) or 0) for f in self.cost_features}])
        e = self.cost_explainer(X)
        base = float(e.base_values[0])
        contrib = [{"feature": f, "label": COST_FEATURE_LABELS.get(f, f), "value": float(X.iloc[0][f]),
                    "contribution": float(v)} for f, v in zip(self.cost_features, e.values[0])]
        contrib.sort(key=lambda d: -abs(d["contribution"]))
        return {"model": "next_year_cost", "version": self.cost_info.version, "unit": "USD",
                "base_value": base, "prediction": base + float(e.values[0].sum()), "contributions": contrib}

    # ---------------------------------------------------------------- fraud model
    def score_claim(self, feats: dict) -> tuple[float, dict]:
        X = pd.DataFrame([feats], columns=FRAUD_FEATURES)
        raw = -float(self.fraud.score_samples(X)[0])
        score = float(np.interp(raw, self.fraud_q, np.linspace(0, 1, len(self.fraud_q))))
        sv = -self.fraud_explainer.shap_values(X)[0]
        contrib = [{"feature": f, "label": FRAUD_LABELS[f], "value": float(feats[f]), "contribution": float(v)}
                   for f, v in zip(FRAUD_FEATURES, sv)]
        contrib.sort(key=lambda d: -abs(d["contribution"]))
        return score, {"model": "claim_fraud", "version": self.fraud_info.version, "unit": "anomaly (path length)",
                       "score": score, "raw": raw, "contributions": contrib}
