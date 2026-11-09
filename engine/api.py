"""HTTP API for the decision engine.

    uv run uvicorn engine.api:app --port 8000          # docs at http://localhost:8000/docs
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from contextlib import asynccontextmanager
from typing import Literal

import mlflow
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine import db, simulator
from engine.codes import CHRONIC_LABELS, label
from engine.config import COMPANY, MLFLOW_UI
from engine.db import Jsonb
from engine.models import Models
from engine.rules import SEVERITY, evaluate
from engine.service import FACT_ROOTS, Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("engine.api")
STATE: dict = {}
Flow = Literal["claim", "prior_auth"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    db.open_pool()
    models = Models()
    models.ensure_member_risk()
    STATE["models"], STATE["engine"] = models, Engine(models)
    STATE["importance"] = {
        "next_year_cost": mlflow.artifacts.load_dict(f"runs:/{models.cost_info.run_id}/feature_importance.json"),
        "claim_fraud": mlflow.artifacts.load_dict(f"runs:/{models.fraud_info.run_id}/shap_importance.json"),
    }
    log.info("decision engine ready in %.1fs (models %s)", time.time() - t0, models.versions())
    yield
    db.pool.close()


app = FastAPI(title=f"{COMPANY} decision engine", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def E() -> Engine:
    return STATE["engine"]


# ------------------------------------------------------------------------------------ schemas
class Line(BaseModel):
    line_num: int | None = None
    hcpcs: str | None
    amount: float
    dx: str | None = None


class Claim(BaseModel):
    claim_id: str
    member_id: str
    provider_npi: str | None = None
    service_date: dt.date
    dx_codes: list[str] = []
    lines: list[Line] = Field(min_length=1)


class PriorAuthRequest(BaseModel):
    member_id: str
    code: str
    kind: Literal["hcpcs", "drg"] = "hcpcs"
    units: int = Field(1, ge=1, le=99)
    provider_npi: str | None = None


class SimRequest(BaseModel):
    claims: int = Field(100, ge=0, le=1000)
    fraud_rate: float = Field(0.1, ge=0, le=1)
    prior_auths: int = Field(20, ge=0, le=500)


class Review(BaseModel):
    action: Literal["approve", "deny"]
    note: str = ""


class RulesBody(BaseModel):
    default: dict | None = None
    rules: list[dict]
    note: str = ""


class BacktestRequest(RulesBody):
    limit: int = Field(2000, ge=10, le=20000)


# ------------------------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta():
    m: Models = STATE["models"]
    return {"company": COMPANY, "today": "2010-07-01", "mlflow_ui": MLFLOW_UI, "models": m.versions(),
            "rulesets": {f: E().active_ruleset(f)["version"] for f in ("claim", "prior_auth")}}


@app.get("/api/models")
def models():
    m: Models = STATE["models"]
    return [
        {**m.cost_info.card(), "title": "Next-year cost", "kind": "Gradient boosting (Poisson)",
         "purpose": "Expected total cost of care next year; drives member risk tiers used by prior-auth rules.",
         "explainer": "SHAP permutation (dollar contributions)", "importance": STATE["importance"]["next_year_cost"]},
        {**m.fraud_info.card(), "title": "Claim anomaly (fraud)", "kind": "Isolation Forest (unsupervised)",
         "purpose": "How unusual a professional claim is vs. normal claims; feeds SIU and payment-integrity rules.",
         "explainer": "SHAP tree explainer (anomaly contributions)", "importance": STATE["importance"]["claim_fraud"]},
    ]


# ------------------------------------------------------------------------------------ decisions
@app.post("/api/claims/decide")
def decide_claim(claim: Claim):
    return E().decide_claim(claim.model_dump(mode="json"))


@app.post("/api/prior-auth")
def decide_prior_auth(req: PriorAuthRequest):
    if not db.q1("SELECT 1 FROM member_snapshot WHERE member_id = %s", (req.member_id,)):
        raise HTTPException(404, "member not found")
    return E().decide_prior_auth(req.model_dump())


@app.get("/api/prior-auth/catalog")
def pa_catalog():
    return E().catalog()


@app.post("/api/simulate")
def simulate(req: SimRequest):
    t0 = time.time()
    claims = simulator.run_claims(E(), req.claims, req.fraud_rate) if req.claims else []
    pas = simulator.run_prior_auths(E(), req.prior_auths) if req.prior_auths else []
    summary: dict = {}
    for r in claims + pas:
        summary.setdefault(r["flow"], {}).setdefault(r["outcome"], 0)
        summary[r["flow"]][r["outcome"]] += 1
    return {"processed": len(claims) + len(pas), "seconds": round(time.time() - t0, 1), "outcomes": summary,
            "avg_latency_ms": round(sum(r["latency_ms"] for r in claims + pas) / max(1, len(claims) + len(pas)), 1)}


@app.get("/api/decisions")
def list_decisions(flow: Flow | None = None, outcome: str | None = None, queue: str | None = None,
                   review_status: str | None = None, injected: str | None = None, q: str | None = None,
                   limit: int = Query(50, le=500), offset: int = 0):
    where, p = ["true"], {}
    for col, val in (("flow", flow), ("outcome", outcome), ("queue", queue), ("review_status", review_status)):
        if val:
            where.append(f"{col} = %({col})s"); p[col] = val
    if injected == "any":
        where.append("injected IS NOT NULL")
    elif injected == "none":
        where.append("injected IS NULL")
    elif injected:
        where.append("injected = %(inj)s"); p["inj"] = injected
    if q:
        where.append("(subject_id ILIKE %(q)s OR member_id ILIKE %(q)s)"); p["q"] = f"%{q}%"
    w = " AND ".join(where)
    rows = db.q(f"""SELECT id, flow, subject_id, member_id, created_at, outcome, queue, amount, reasons,
                           (facts->'fraud'->>'score')::float AS fraud_score, facts->'member'->>'risk_tier' AS risk_tier,
                           facts->'request'->>'label' AS procedure, request->>'service_date' AS service_date,
                           injected, review_status, review_outcome, latency_ms
                    FROM decision WHERE {w} ORDER BY id DESC LIMIT %(limit)s OFFSET %(offset)s""",
                {**p, "limit": limit, "offset": offset})
    total = db.q1(f"SELECT count(*) AS n FROM decision WHERE {w}", p)["n"]
    return {"total": total, "items": rows}


@app.get("/api/decisions/{decision_id}")
def get_decision(decision_id: int):
    d = db.q1("SELECT * FROM decision WHERE id = %s", (decision_id,))
    if not d:
        raise HTTPException(404, "decision not found")
    if d["flow"] == "claim":
        prices = E().prices
        for l in d["request"]["lines"]:
            p50, p95 = prices.get(l.get("hcpcs"), (None, None))
            l.update({"label": label(l.get("hcpcs")), "p50": p50, "p95": p95,
                      "price_ratio": (l["amount"] / max(p50, 10)) if p50 else None})
        d["request"]["dx_labels"] = {c: label(c, "icd9") for c in d["request"].get("dx_codes", [])}
    return d


@app.post("/api/decisions/{decision_id}/review")
def review(decision_id: int, body: Review):
    row = db.q1("""UPDATE decision SET review_status = 'resolved', review_outcome = %s, review_note = %s,
                   reviewed_at = now() WHERE id = %s RETURNING id, review_status, review_outcome""",
                ("APPROVE" if body.action == "approve" else "DENY", body.note, decision_id))
    if not row:
        raise HTTPException(404, "decision not found")
    return row


# ------------------------------------------------------------------------------------ dashboard
@app.get("/api/dashboard")
def dashboard():
    outcomes = db.q("""SELECT flow, outcome, count(*) AS n, coalesce(sum(amount), 0) AS amount
                       FROM decision GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    queues = db.q("""SELECT flow, queue, count(*) AS n, coalesce(sum(amount), 0) AS amount FROM decision
                     WHERE review_status = 'open' GROUP BY 1, 2 ORDER BY 3 DESC""")
    fraud = db.q("""SELECT coalesce(injected, 'genuine') AS scenario, outcome, count(*) AS n FROM decision
                    WHERE flow = 'claim' GROUP BY 1, 2""")
    caught_by = db.q("""SELECT d.injected AS scenario, r->>'rule' AS rule, count(*) AS n
                        FROM decision d, jsonb_array_elements(d.reasons) WITH ORDINALITY AS x(r, i)
                        WHERE d.flow = 'claim' AND d.injected IS NOT NULL AND i = 1 GROUP BY 1, 2""")
    totals = db.q1("""SELECT count(*) FILTER (WHERE flow = 'claim') AS claims,
                             count(*) FILTER (WHERE flow = 'prior_auth') AS prior_auths,
                             avg(latency_ms) FILTER (WHERE flow = 'claim') AS claim_latency,
                             avg(latency_ms) FILTER (WHERE flow = 'prior_auth') AS pa_latency,
                             count(*) FILTER (WHERE review_status = 'open') AS open_reviews,
                             count(*) FILTER (WHERE review_status = 'resolved') AS resolved_reviews
                      FROM decision""")
    series = db.q("""SELECT date_trunc('minute', created_at) AS t, flow, outcome, count(*) AS n FROM decision
                     WHERE created_at > now() - interval '24 hours' GROUP BY 1, 2, 3 ORDER BY 1""")
    return {"totals": totals, "outcomes": outcomes, "queues": queues, "fraud_matrix": fraud,
            "caught_by": caught_by, "series": series}


# ------------------------------------------------------------------------------------ members
@app.get("/api/members")
def members(q: str | None = None, tier: str | None = None, limit: int = Query(50, le=200)):
    where, p = ["true"], {"limit": limit}
    if q:
        where.append("s.member_id ILIKE %(q)s"); p["q"] = f"{q}%"
    if tier:
        where.append("r.risk_tier = %(tier)s"); p["tier"] = tier
    rows = db.q(f"""SELECT s.member_id, 2010 - extract(year FROM s.birth_date)::int AS age, s.sex, s.state, s.n_chronic,
                           s.death_date, r.predicted_cost, r.risk_pct, r.risk_tier,
                           s.ip_cost + s.op_cost + s.car_cost + s.rx_cost AS cost_2009
                    FROM member_snapshot s JOIN member_risk r USING (member_id)
                    WHERE {" AND ".join(where)} ORDER BY r.predicted_cost DESC LIMIT %(limit)s""", p)
    tiers = db.q("""SELECT risk_tier, count(*) AS n, avg(predicted_cost) AS avg_cost FROM member_risk
                    GROUP BY 1 ORDER BY 3""")
    return {"items": rows, "tiers": tiers}


@app.get("/api/members/{member_id}")
def member(member_id: str):
    facts, row = E().member_facts(member_id, dt.date(2010, 7, 1))
    if not row:
        raise HTTPException(404, "member not found")
    years = db.q("""SELECT year, medreimb_ip + benres_ip + pppymt_ip AS inpatient,
                           medreimb_op + benres_op + pppymt_op AS outpatient,
                           medreimb_car + benres_car + pppymt_car AS physician,
                           (SELECT coalesce(sum(tot_rx_cst_amt), 0) FROM synpuf.rx_event r
                            WHERE r.desynpuf_id = b.desynpuf_id AND extract(year FROM r.srvc_dt) = b.year) AS drugs
                    FROM synpuf.beneficiary_year b WHERE desynpuf_id = %s ORDER BY year""", (member_id,))
    stays = db.q("""SELECT clm_id, clm_from_dt, clm_thru_dt, clm_drg_cd, clm_pmt_amt, icd9_dgns_cds[1] AS dx
                    FROM synpuf.inpatient_claim WHERE desynpuf_id = %s ORDER BY clm_from_dt DESC LIMIT 10""", (member_id,))
    for s in stays:
        s["drg_label"], s["dx_label"] = label(s["clm_drg_cd"], "drg"), label(s["dx"], "icd9")
    decisions = db.q("""SELECT id, flow, subject_id, created_at, outcome, queue, amount, injected FROM decision
                        WHERE member_id = %s ORDER BY id DESC LIMIT 20""", (member_id,))
    return {"facts": facts, "snapshot": {k: row[k] for k in row if not k.startswith("sp_")},
            "explanation": STATE["models"].explain_cost(row), "years": years, "inpatient_stays": stays,
            "decisions": decisions, "chronic_labels": CHRONIC_LABELS}


# ------------------------------------------------------------------------------------ rules
@app.get("/api/rules/{flow}")
def get_rules(flow: Flow):
    active = E().active_ruleset(flow)
    versions = db.q("SELECT version, note, created_at, is_active FROM ruleset WHERE flow = %s ORDER BY version DESC", (flow,))
    fires = db.q("""SELECT t->>'id' AS rule, count(*) FILTER (WHERE (t->>'matched')::bool) AS fired, count(*) AS evaluated
                    FROM (SELECT rule_trace FROM decision WHERE flow = %s ORDER BY id DESC LIMIT 2000) d,
                         jsonb_array_elements(d.rule_trace) t GROUP BY 1""", (flow,))
    return {"active": active, "versions": versions, "fire_stats": {f["rule"]: f for f in fires},
            "outcomes": list(SEVERITY[flow]), "fact_roots": sorted(FACT_ROOTS[flow]),
            "sample_facts": (db.q1("SELECT facts FROM decision WHERE flow = %s ORDER BY id DESC LIMIT 1", (flow,)) or {}).get("facts")}


@app.get("/api/rules/{flow}/versions/{version}")
def get_rule_version(flow: Flow, version: int):
    r = db.q1("SELECT version, body, note, created_at, is_active FROM ruleset WHERE flow = %s AND version = %s", (flow, version))
    if not r:
        raise HTTPException(404)
    return r


@app.post("/api/rules/{flow}/validate")
def validate_rules(flow: Flow, body: RulesBody):
    return {"problems": E().validate(flow, body.model_dump())}


@app.post("/api/rules/{flow}/backtest")
def backtest(flow: Flow, body: BacktestRequest):
    """Re-run the active and the candidate rulesets on stored facts of recent decisions (models
    are not re-scored: scores are part of the stored facts), and diff the outcomes."""
    problems = E().validate(flow, body.model_dump())
    if problems:
        raise HTTPException(422, {"problems": problems})
    rows = db.q("SELECT id, subject_id, amount, facts, injected FROM decision WHERE flow = %s ORDER BY id DESC LIMIT %s",
                (flow, body.limit))
    active = E().active_ruleset(flow)
    cand = {"default": body.default or active.get("default"), "rules": body.rules}
    matrix: dict = {}
    changed, fires = [], {r["id"]: 0 for r in body.rules}
    stats = {k: {"flagged_fraud": 0, "flagged_genuine": 0, "held_amount": 0.0, "auto": 0} for k in ("current", "candidate")}
    n_fraud = sum(1 for r in rows if r["injected"])
    for r in rows:
        a = evaluate(active, r["facts"], flow)
        b = evaluate(cand, r["facts"], flow)
        for t in b["trace"]:
            if t["matched"]:
                fires[t["id"]] = fires.get(t["id"], 0) + 1
        for k, res in (("current", a), ("candidate", b)):
            if res["outcome"] == "APPROVE":
                stats[k]["auto"] += 1
            else:
                stats[k]["held_amount"] += float(r["amount"] or 0)
                stats[k]["flagged_fraud" if r["injected"] else "flagged_genuine"] += 1
        key = f"{a['outcome']}|{b['outcome']}"
        matrix[key] = matrix.get(key, 0) + 1
        if a["outcome"] != b["outcome"] and len(changed) < 100:
            changed.append({"id": r["id"], "subject_id": r["subject_id"], "amount": r["amount"], "injected": r["injected"],
                            "from": a["outcome"], "to": b["outcome"], "rule": b["reasons"][0]["name"]})
    return {"evaluated": len(rows), "injected_total": n_fraud, "matrix": matrix, "changed": changed,
            "changed_total": sum(v for k, v in matrix.items() if k.split("|")[0] != k.split("|")[1]),
            "rule_fires": fires, "stats": stats}


@app.post("/api/rules/{flow}/publish")
def publish(flow: Flow, body: RulesBody):
    try:
        v = E().publish(flow, body.model_dump(), body.note or "Edited in web app")
    except ValueError as e:
        raise HTTPException(422, {"problems": e.args[0]})
    return {"version": v}


@app.post("/api/rules/{flow}/activate/{version}")
def activate(flow: Flow, version: int):
    r = db.q1("SELECT body FROM ruleset WHERE flow = %s AND version = %s", (flow, version))
    if not r:
        raise HTTPException(404)
    return {"version": E().publish(flow, r["body"], f"Rollback to v{version}")}


@app.post("/api/admin/reset")
def reset():
    """Clear simulated decisions (keeps rules and models)."""
    db.execute("TRUNCATE decision, incoming_claim RESTART IDENTITY CASCADE")
    return {"ok": True}
