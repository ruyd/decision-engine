"""Train the claim anomaly (fraud) model and log it to MLflow.

    uv run python -m fraud_model.train

Unsupervised: an Isolation Forest learns what ordinary 2009 professional claims look like.
Evaluation: 2010 claims (new period) plus copies with injected fraud patterns; we measure how
well the score separates each pattern from normal claims. Registered as claim_fraud@champion.
The raw anomaly score is mapped to a 0-1 percentile of the training distribution, so
fraud_score = 0.99 means "more unusual than 99% of normal claims".
"""
from __future__ import annotations

import json
import random
import tempfile
import time
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import shap
from mlflow.models import infer_signature
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from skops.io import dumps, get_untrusted_types

from engine.config import LAKE_DB, MLFLOW_URI, REF, SAMPLES
from fraud_model.features import FEATURES, LABELS, claim_features
from fraud_model.injection import MODEL_SCENARIOS, SCENARIOS, inject

EXPERIMENT, REGISTERED = "claim-fraud", "claim_fraud"
N_TRAIN, N_EVAL, N_INJECT = 300_000, 20_000, 2_000
S = ",".join(map(str, SAMPLES))


def sample_claims(con: duckdb.DuckDBPyConnection, year: int, n: int, seed: int) -> list[tuple[dict, dict]]:
    """Real carrier claims with lines + the same context the live engine looks up."""
    con.execute(f"""CREATE OR REPLACE TEMP TABLE t AS
        SELECT * FROM (
            SELECT sample_id, clm_id, desynpuf_id, clm_from_dt, icd9_dgns_cds FROM synpuf.carrier_claim
            WHERE sample_id IN ({S}) AND year(clm_from_dt) = {year})
        USING SAMPLE reservoir({n} ROWS) REPEATABLE ({seed})""")   # sample AFTER filtering
    rows = con.execute(f"""
    WITH
    lines AS (SELECT l.clm_id, list(struct_pack(line_num := l.line_num, hcpcs := l.hcpcs_cd,
                     amount := l.line_nch_pmt_amt::DOUBLE, dx := l.line_icd9_dgns_cd) ORDER BY l.line_num) AS lines,
                     mode(l.prf_physn_npi) AS npi,
                     string_agg(coalesce(l.hcpcs_cd, '-'), '|' ORDER BY coalesce(l.hcpcs_cd, '-')) AS sig
              FROM synpuf.carrier_line l JOIN t USING (sample_id, clm_id) GROUP BY 1),
    vel AS (SELECT t.clm_id, count(c.clm_id) AS member_claims_30d FROM t
            LEFT JOIN synpuf.carrier_claim c ON c.desynpuf_id = t.desynpuf_id
             AND c.clm_from_dt >= t.clm_from_dt - INTERVAL 30 DAY AND c.clm_from_dt < t.clm_from_dt
            GROUP BY 1),
    same_day AS (SELECT t.clm_id AS clm_id, c.clm_id AS other_id FROM t
                 JOIN synpuf.carrier_claim c ON c.desynpuf_id = t.desynpuf_id AND c.clm_from_dt = t.clm_from_dt
                  AND c.clm_id <> t.clm_id),
    other_sig AS (SELECT s.clm_id, s.other_id,
                         string_agg(coalesce(l.hcpcs_cd, '-'), '|' ORDER BY coalesce(l.hcpcs_cd, '-')) AS sig
                  FROM same_day s JOIN synpuf.carrier_line l ON l.clm_id = s.other_id GROUP BY 1, 2),
    dup AS (SELECT o.clm_id, count(*) AS dup_count FROM other_sig o JOIN lines USING (clm_id)
            WHERE o.sig = lines.sig GROUP BY 1)
    SELECT t.clm_id, t.desynpuf_id, t.clm_from_dt::VARCHAR, t.icd9_dgns_cds, lines.lines, lines.npi,
           coalesce(vel.member_claims_30d, 0), coalesce(dup.dup_count, 0),
           p.prov_claims, p.prov_lines_per_member, p.prov_paid_per_line, p.prov_high_em_share,
           p.prov_lab_share, p.prov_distinct_hcpcs
    FROM t JOIN lines USING (clm_id) LEFT JOIN vel USING (clm_id) LEFT JOIN dup USING (clm_id)
    LEFT JOIN read_parquet('{REF / "ref_provider_profile.parquet"}') p ON p.npi = lines.npi
    """).fetchall()
    out = []
    for (cid, mid, dt, dx, lines, npi, vel, dup, pc, plpm, pppl, pem, plab, pdh) in rows:
        claim = {"claim_id": cid, "member_id": mid, "provider_npi": npi, "service_date": dt,
                 "dx_codes": list(dx or []), "lines": [dict(l) for l in lines]}
        prov = None if pc is None else dict(prov_claims=pc, prov_lines_per_member=plpm, prov_paid_per_line=pppl,
                                            prov_high_em_share=pem, prov_lab_share=plab, prov_distinct_hcpcs=pdh)
        out.append((claim, {"member_claims_30d": vel, "dup_count": dup, "provider": prov}))
    return out


def to_frame(items, prices) -> pd.DataFrame:
    return pd.DataFrame([claim_features(c, ctx, prices) for c, ctx in items], columns=FEATURES)


def main() -> None:
    t0 = time.time()
    con = duckdb.connect()
    con.execute(f"SET memory_limit='5GB'; SET threads=6; SET temp_directory='{REF.parent / 'tmp'}';")
    con.execute(f"ATTACH '{LAKE_DB}' AS lake (READ_ONLY); USE lake;")
    prices = {r[0]: (r[1], r[2]) for r in con.execute(
        f"SELECT hcpcs_cd, p50_amt, p95_amt FROM read_parquet('{REF / 'ref_hcpcs_price.parquet'}')").fetchall()}
    train_items = sample_claims(con, 2009, N_TRAIN, seed=1)
    eval_items = sample_claims(con, 2010, N_EVAL + N_INJECT * len(MODEL_SCENARIOS), seed=2)
    print(f"sampled {len(train_items):,} train / {len(eval_items):,} eval claims in {time.time() - t0:.0f}s")

    X_train = to_frame(train_items, prices)
    rng = random.Random(7)
    normal, pool = eval_items[:N_EVAL], eval_items[N_EVAL:]
    injected = []
    for i, scen in enumerate(MODEL_SCENARIOS):
        for claim, ctx in pool[i * N_INJECT:(i + 1) * N_INJECT]:
            ctx2 = dict(ctx, dup_count=ctx["dup_count"] + 1) if scen == "duplicate" else ctx
            injected.append((inject(claim, scen, prices, rng), ctx2, scen))
    X_norm = to_frame(normal, prices)
    X_inj = to_frame([(c, ctx) for c, ctx, _ in injected], prices)
    scen_labels = np.array([s for _, _, s in injected])

    mlflow.set_tracking_uri(MLFLOW_URI)
    mlflow.set_experiment(EXPERIMENT)
    params = dict(n_estimators=300, max_samples=2048, max_features=1.0, random_state=42)
    with mlflow.start_run(run_name="isolation_forest",
                          description="Unsupervised anomaly model over professional claims; "
                                      "evaluated on 2010 claims with injected fraud patterns.") as run:
        mlflow.log_params({**params, "features": ",".join(FEATURES), "train_rows": len(X_train),
                           "train_period": "2009", "eval_period": "2010", "eval_normal": len(X_norm),
                           "eval_injected_per_scenario": N_INJECT})
        model = IsolationForest(**params, n_jobs=-1).fit(X_train)
        anomaly_train = -model.score_samples(X_train)
        quantiles = np.quantile(anomaly_train, np.linspace(0, 1, 1001))

        def fraud_score(X):
            return np.interp(-model.score_samples(X), quantiles, np.linspace(0, 1, 1001))

        s_norm, s_inj = fraud_score(X_norm), fraud_score(X_inj)
        metrics = {}
        for thr in (0.99, 0.995):
            metrics[f"normal_flag_rate_at_{thr}"] = float((s_norm >= thr).mean())
            metrics[f"recall_all_at_{thr}"] = float((s_inj >= thr).mean())
        for scen in MODEL_SCENARIOS:
            si = s_inj[scen_labels == scen]
            y = np.r_[np.zeros(len(s_norm)), np.ones(len(si))]
            metrics[f"auc_{scen}"] = float(roc_auc_score(y, np.r_[s_norm, si]))
            metrics[f"recall_{scen}_at_0.99"] = float((si >= 0.99).mean())
        mlflow.log_metrics(metrics)

        # SHAP: which features drive the anomaly score on the injected claims
        expl = shap.TreeExplainer(model)
        sv = -expl.shap_values(X_inj.sample(1500, random_state=0))    # sign flip: + = more anomalous
        imp = pd.Series(np.abs(sv).mean(0), index=FEATURES).sort_values()
        with tempfile.TemporaryDirectory() as tmp:
            fig, ax = plt.subplots(figsize=(6.5, 5))
            imp.rename(LABELS).plot.barh(ax=ax)
            ax.set_xlabel("mean |SHAP| on injected-fraud claims")
            fig.tight_layout(); fig.savefig(Path(tmp) / "shap_importance.png", dpi=110); plt.close(fig)
            fig, ax = plt.subplots(figsize=(6.5, 4))
            ax.hist(s_norm, bins=50, alpha=.6, label="normal 2010 claims", density=True)
            ax.hist(s_inj, bins=50, alpha=.6, label="injected fraud", density=True)
            ax.set_xlabel("fraud score (percentile of normal 2009 claims)"); ax.legend()
            fig.tight_layout(); fig.savefig(Path(tmp) / "score_distribution.png", dpi=110); plt.close(fig)
            mlflow.log_artifacts(tmp, "plots")
        mlflow.log_dict({"quantiles": quantiles.tolist()}, "score_quantiles.json")
        mlflow.log_dict({"features": FEATURES, "labels": LABELS}, "features.json")
        mlflow.log_dict(imp.sort_values(ascending=False).round(5).to_dict(), "shap_importance.json")

        example = X_norm.head(5)
        trusted = get_untrusted_types(data=dumps(model))   # our own freshly trained model
        mlflow.sklearn.log_model(model, name="model", input_example=example,
                                 signature=infer_signature(example, model.score_samples(example)),
                                 skops_trusted_types=trusted)
        mv = mlflow.register_model(f"runs:/{run.info.run_id}/model", REGISTERED)
        mlflow.MlflowClient().set_registered_model_alias(REGISTERED, "champion", mv.version)

    print(f"done in {time.time() - t0:.0f}s; registered {REGISTERED} v{mv.version} as champion")
    for k, v in metrics.items():
        print(f"  {k:32s} {v:.3f}")
    print("  top SHAP drivers:", list(imp.sort_values(ascending=False).index[:6]))


if __name__ == "__main__":
    main()
