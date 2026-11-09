"""Decision service: builds facts for a claim or prior-auth request, scores models, runs rules,
persists the full decision record (facts + explanations + rule trace) for audit and backtesting.
"""
from __future__ import annotations

import datetime as dt
import time
import uuid
from functools import lru_cache
from pathlib import Path

import yaml

from engine import db
from engine.codes import CHRONIC_LABELS, category_for, label
from engine.db import Jsonb
from engine.models import Models
from engine.rules import evaluate, validate_rules
from fraud_model.features import claim_features, claim_signature

TODAY = dt.date(2010, 7, 1)       # the simulated "current date" for prior-auth requests
FACT_ROOTS = {"claim": {"claim", "member", "provider", "fraud"},
              "prior_auth": {"request", "member", "provider"}}
CHRONIC = list(CHRONIC_LABELS)


class Engine:
    def __init__(self, models: Models) -> None:
        self.models = models
        self.prices = {r["hcpcs_cd"]: (float(r["p50_amt"]), float(r["p95_amt"]))
                       for r in db.q("SELECT hcpcs_cd, p50_amt, p95_amt FROM ref_hcpcs_price")}
        self.drg = {r["drg_cd"]: r for r in db.q("SELECT * FROM ref_drg_price")}
        self._seed_rules()

    # ------------------------------------------------------------------ rules storage
    def _seed_rules(self) -> None:
        seed = yaml.safe_load((Path(__file__).parent / "default_rules.yaml").read_text())
        for flow, body in seed.items():
            if not db.q1("SELECT 1 FROM ruleset WHERE flow = %s", (flow,)):
                db.q("INSERT INTO ruleset (flow, version, body, note, is_active) VALUES (%s, 1, %s, %s, true) RETURNING id",
                     (flow, Jsonb(body), "Seed rules"))

    def active_ruleset(self, flow: str) -> dict:
        r = db.q1("SELECT version, body FROM ruleset WHERE flow = %s AND is_active", (flow,))
        return {"version": r["version"], **r["body"]}

    def validate(self, flow: str, body: dict) -> list[dict]:
        return validate_rules(body.get("rules", []), flow, FACT_ROOTS[flow])

    def publish(self, flow: str, body: dict, note: str) -> int:
        problems = self.validate(flow, body)
        if problems:
            raise ValueError(problems)
        with db.conn() as c, c.transaction():
            v = c.execute("SELECT coalesce(max(version), 0) + 1 AS v FROM ruleset WHERE flow = %s", (flow,)).fetchone()["v"]
            c.execute("UPDATE ruleset SET is_active = false WHERE flow = %s", (flow,))
            c.execute("INSERT INTO ruleset (flow, version, body, note, is_active) VALUES (%s, %s, %s, %s, true)",
                      (flow, v, Jsonb({"default": body.get("default"), "rules": body["rules"]}), note))
        return v

    # ------------------------------------------------------------------ member facts
    def member_facts(self, member_id: str, on_date: dt.date) -> tuple[dict, dict | None]:
        m = db.q1("""SELECT s.*, r.predicted_cost, r.risk_pct, r.risk_tier FROM member_snapshot s
                     LEFT JOIN member_risk r USING (member_id) WHERE s.member_id = %s""", (member_id,))
        cov = db.q1("""SELECT max(bene_death_dt) AS death,
                              max(bene_smi_cvrage_tot_mons) FILTER (WHERE year = %(y)s) AS partb,
                              max(bene_hi_cvrage_tot_mons) FILTER (WHERE year = %(y)s) AS parta
                       FROM synpuf.beneficiary_year WHERE desynpuf_id = %(m)s""", {"y": on_date.year, "m": member_id})
        if not m:
            return {"id": member_id, "found": False, "deceased": False, "deceased_before_service": False,
                    "partb_months": None, "parta_months": None, "risk_tier": None, "predicted_cost": None,
                    "n_chronic": 0, "age": None}, None
        death = cov["death"] if cov and cov["death"] else m["death_date"]
        facts = {
            "id": member_id, "found": True,
            "age": on_date.year - m["birth_date"].year, "sex": {1: "M", 2: "F"}.get(m["sex"]),
            "state": m["state"], "esrd": bool(m["esrd"]),
            "death_date": death.isoformat() if death else None,
            "deceased": bool(death and death <= on_date),
            "deceased_before_service": bool(death and death < on_date),
            "partb_months": cov["partb"] if cov and cov["partb"] is not None else m["partb_months"],
            "parta_months": cov["parta"] if cov and cov["parta"] is not None else m["parta_months"],
            "partd_months": m["partd_months"],
            "predicted_cost": float(m["predicted_cost"]) if m["predicted_cost"] is not None else None,
            "risk_pct": float(m["risk_pct"]) if m["risk_pct"] is not None else None,
            "risk_tier": m["risk_tier"], "n_chronic": m["n_chronic"],
            "chronic": [CHRONIC_LABELS[c] for c in CHRONIC if m[c]],
            **{c.removeprefix("sp_"): bool(m[c]) for c in CHRONIC},
        }
        return facts, m

    # ------------------------------------------------------------------ claims
    def claim_context(self, claim: dict) -> dict:
        d = dt.date.fromisoformat(claim["service_date"])
        sig = claim_signature(claim["lines"])
        mid, cid = claim["member_id"], claim["claim_id"]
        vel = db.q1("""SELECT (SELECT count(*) FROM synpuf.carrier_claim
                               WHERE desynpuf_id = %(m)s AND clm_from_dt >= %(d)s::date - 30 AND clm_from_dt < %(d)s)
                            + (SELECT count(*) FROM incoming_claim WHERE member_id = %(m)s AND NOT in_history
                               AND service_date >= %(d)s::date - 30 AND service_date < %(d)s) AS n""",
                    {"m": mid, "d": d})["n"]
        dup = db.q1("""SELECT (SELECT count(*) FROM (
                                 SELECT string_agg(coalesce(l.hcpcs_cd, '-'), '|' ORDER BY coalesce(l.hcpcs_cd, '-') COLLATE "C") AS sig
                                 FROM synpuf.carrier_claim c
                                 JOIN synpuf.carrier_line l ON l.sample_id = c.sample_id AND l.clm_id = c.clm_id
                                 WHERE c.desynpuf_id = %(m)s AND c.clm_from_dt = %(d)s AND c.clm_id <> %(c)s
                                 GROUP BY c.clm_id) s WHERE s.sig = %(s)s)
                            + (SELECT count(*) FROM incoming_claim WHERE member_id = %(m)s AND service_date = %(d)s
                               AND signature = %(s)s AND claim_id <> %(c)s AND NOT in_history) AS n""",
                    {"m": mid, "d": d, "c": cid, "s": sig})["n"]
        prov = db.q1("SELECT * FROM ref_provider_profile WHERE npi = %s", (claim.get("provider_npi"),)) \
            if claim.get("provider_npi") else None
        return {"member_claims_30d": int(vel), "dup_count": int(dup), "provider": prov, "signature": sig}

    def decide_claim(self, claim: dict, injected: str | None = None, in_history: bool = False) -> dict:
        t0 = time.perf_counter()
        d = dt.date.fromisoformat(claim["service_date"])
        ctx = self.claim_context(claim)
        feats = claim_features(claim, ctx, self.prices)
        score, fraud_expl = self.models.score_claim(feats)
        member, _ = self.member_facts(claim["member_id"], d)
        prov = ctx["provider"]
        facts = {
            "claim": {"id": claim["claim_id"], "service_date": claim["service_date"],
                      "hcpcs": [l.get("hcpcs") for l in claim["lines"]], "dx_codes": claim.get("dx_codes", []),
                      **{k: feats[k] for k in ("total_paid", "n_lines", "n_distinct_hcpcs", "max_price_ratio",
                                               "n_lines_above_p95", "high_em_lines", "lab_lines", "n_dx",
                                               "member_claims_30d", "dup_count")}},
            "member": member,
            "provider": {"npi": claim.get("provider_npi"), "known": prov is not None,
                         "claims": prov["prov_claims"] if prov else 0,
                         "high_em_share": float(prov["prov_high_em_share"] or 0) if prov else 0.0,
                         "paid_per_line": float(prov["prov_paid_per_line"] or 0) if prov else None,
                         "lines_per_member": float(prov["prov_lines_per_member"] or 0) if prov else None,
                         "lab_share": float(prov["prov_lab_share"] or 0) if prov else None},
            "fraud": {"score": round(score, 4),
                      "top_factor": fraud_expl["contributions"][0]["label"]},
        }
        ruleset = self.active_ruleset("claim")
        result = evaluate(ruleset, facts, "claim")
        latency = (time.perf_counter() - t0) * 1000
        return self._store("claim", claim["claim_id"], claim["member_id"], feats["total_paid"], claim, facts,
                           {"fraud": fraud_expl}, result, ruleset["version"], latency, injected,
                           incoming=(claim["claim_id"], claim["member_id"], d, ctx["signature"], in_history))

    # ------------------------------------------------------------------ prior auth
    @lru_cache(maxsize=1)
    def catalog(self) -> list[dict]:
        rows = db.q("""SELECT hcpcs_cd AS code, 'hcpcs' AS kind, n_lines AS volume, p50_amt, p95_amt FROM ref_hcpcs_price
                       WHERE n_lines >= 300 AND (hcpcs_cd ~ '^(7[0-9]|[1-6][0-9])' OR hcpcs_cd ~ '^[EJK]')
                       UNION ALL
                       SELECT drg_cd, 'drg', n_claims, p50_amt, p95_amt FROM ref_drg_price WHERE n_claims >= 150
                       ORDER BY volume DESC""")
        out = []
        for r in rows:
            cat = category_for(r["code"], r["kind"])
            if cat in ("lab", "medicine", "other", "transport"):
                continue
            out.append({"code": r["code"], "kind": r["kind"], "category": cat,
                        "label": label(r["code"], r["kind"]) or (f"DRG {r['code']}" if r["kind"] == "drg" else r["code"]),
                        "volume": r["volume"], "typical_cost": float(r["p50_amt"]), "high_cost": float(r["p95_amt"])})
        return out

    def decide_prior_auth(self, req: dict, injected: str | None = None) -> dict:
        t0 = time.perf_counter()
        req = {"request_id": req.get("request_id") or f"PA-{uuid.uuid4().hex[:10].upper()}",
               "units": int(req.get("units") or 1), "service_date": req.get("service_date") or TODAY.isoformat(), **req}
        item = next((c for c in self.catalog() if c["code"] == req["code"] and c["kind"] == req["kind"]), None)
        if item is None:
            ref = self.prices.get(req["code"]) if req["kind"] == "hcpcs" else None
            item = {"code": req["code"], "kind": req["kind"], "category": category_for(req["code"], req["kind"]),
                    "label": label(req["code"], req["kind"]) or req["code"],
                    "typical_cost": ref[0] if ref else 0.0, "high_cost": ref[1] if ref else 0.0}
        member, mrow = self.member_facts(req["member_id"], TODAY)
        facts = {
            "request": {"id": req["request_id"], "code": item["code"], "kind": item["kind"], "label": item["label"],
                        "category": item["category"], "units": req["units"],
                        "est_cost": round(item["typical_cost"] * req["units"], 2),
                        "high_cost": round(item["high_cost"] * req["units"], 2)},
            "member": member,
            "provider": {"npi": req.get("provider_npi")},
        }
        expl = {"cost": self.models.explain_cost(mrow)} if mrow else {}
        ruleset = self.active_ruleset("prior_auth")
        result = evaluate(ruleset, facts, "prior_auth")
        latency = (time.perf_counter() - t0) * 1000
        return self._store("prior_auth", req["request_id"], req["member_id"], facts["request"]["est_cost"], req,
                           facts, expl, result, ruleset["version"], latency, injected)

    # ------------------------------------------------------------------ persistence
    def _store(self, flow, subject, member_id, amount, request, facts, expl, result, rs_version, latency,
               injected, incoming=None) -> dict:
        review = "open" if result["outcome"].startswith("PEND") else "none"
        with db.conn() as c, c.transaction():
            row = c.execute(
                """INSERT INTO decision (flow, subject_id, member_id, outcome, queue, amount, reasons, request, facts,
                                         explanations, rule_trace, ruleset_version, model_versions, latency_ms,
                                         injected, review_status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at""",
                (flow, subject, member_id, result["outcome"], result["queue"], amount, Jsonb(result["reasons"]),
                 Jsonb(request), Jsonb(facts), Jsonb(expl), Jsonb(result["trace"]), rs_version,
                 Jsonb(self.models.versions()), round(latency, 1), injected, review)).fetchone()
            if incoming:
                cid, mid, d, sig, hist = incoming
                c.execute("""INSERT INTO incoming_claim (claim_id, member_id, service_date, signature, decision_id, in_history)
                             VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (claim_id) DO NOTHING""",
                          (cid, mid, d, sig, row["id"], hist))
        return {"id": row["id"], "flow": flow, "subject_id": subject, "outcome": result["outcome"],
                "queue": result["queue"], "reasons": result["reasons"], "latency_ms": round(latency, 1),
                "facts": facts, "explanations": expl, "rule_trace": result["trace"], "ruleset_version": rs_version}
