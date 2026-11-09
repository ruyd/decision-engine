"""Traffic simulator: replays real 2010 SynPUF claims as 'incoming' and injects known fraud.

Genuine claims keep their real claim id (they also exist in history, so they're excluded from
their own duplicate check). Injected scenarios:
  upcoding / price_inflation / unbundling : same claim id, fraudulently altered lines
  duplicate                               : exact resubmission under a new claim id
  deceased_member                         : claim moved to a member who died before the service date
"""
from __future__ import annotations

import random
import uuid

from engine import db
from fraud_model.injection import inject

SCENARIO_WEIGHTS = {"upcoding": 0.25, "price_inflation": 0.2, "unbundling": 0.15,
                    "duplicate": 0.25, "deceased_member": 0.15}


def sample_claims(n: int) -> list[dict]:
    heads = db.q("""SELECT c.sample_id, c.clm_id, c.desynpuf_id, c.clm_from_dt, c.icd9_dgns_cds
                    FROM synpuf.carrier_claim c TABLESAMPLE SYSTEM (0.2)
                    WHERE c.clm_from_dt >= '2010-01-01'
                      AND NOT EXISTS (SELECT 1 FROM incoming_claim i WHERE i.claim_id = c.clm_id)
                    LIMIT %s""", (n,))
    if not heads:
        return []
    lines = db.q("""SELECT clm_id, line_num, hcpcs_cd, line_nch_pmt_amt, line_icd9_dgns_cd, prf_physn_npi
                    FROM synpuf.carrier_line WHERE (sample_id, clm_id) IN (SELECT unnest(%s::smallint[]), unnest(%s::text[]))
                    ORDER BY clm_id, line_num""",
                 ([h["sample_id"] for h in heads], [h["clm_id"] for h in heads]))
    by_claim: dict[str, list] = {}
    for l in lines:
        by_claim.setdefault(l["clm_id"], []).append(l)
    out = []
    for h in heads:
        ls = by_claim.get(h["clm_id"], [])
        if not ls:
            continue
        npis = [l["prf_physn_npi"] for l in ls if l["prf_physn_npi"]]
        out.append({"claim_id": h["clm_id"], "member_id": h["desynpuf_id"], "claim_type": "professional",
                    "service_date": h["clm_from_dt"].isoformat(), "dx_codes": list(h["icd9_dgns_cds"] or []),
                    "provider_npi": max(set(npis), key=npis.count) if npis else None,
                    "lines": [{"line_num": l["line_num"], "hcpcs": l["hcpcs_cd"], "amount": float(l["line_nch_pmt_amt"] or 0),
                               "dx": l["line_icd9_dgns_cd"]} for l in ls]})
    return out


def deceased_members(k: int) -> list[dict]:
    return db.q("""SELECT member_id, death_date FROM member_snapshot TABLESAMPLE SYSTEM (20)
                   WHERE death_date BETWEEN '2009-01-01' AND '2009-11-30' LIMIT %s""", (k,))


def run_claims(engine, n: int, fraud_rate: float, seed: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    claims = sample_claims(n)
    dead = deceased_members(max(5, int(n * fraud_rate)))
    results = []
    for claim in claims:
        scenario = None
        if rng.random() < fraud_rate:
            scenario = rng.choices(list(SCENARIO_WEIGHTS), weights=list(SCENARIO_WEIGHTS.values()))[0]
        if scenario is None:
            results.append(engine.decide_claim(claim, None, in_history=True))
            continue
        bad = inject(claim, scenario, engine.prices, rng)
        bad.pop("injected", None)
        hist = True
        if scenario == "duplicate":
            bad["claim_id"] = f"{claim['claim_id']}-R"
            hist = False
        elif scenario == "deceased_member" and dead:
            m = dead.pop()
            bad["member_id"], bad["claim_id"], hist = m["member_id"], f"SIM-{uuid.uuid4().hex[:12].upper()}", False
        results.append(engine.decide_claim(bad, scenario, in_history=hist))
    return results


def run_prior_auths(engine, n: int, seed: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    catalog = engine.catalog()
    weights = [c["volume"] ** 0.5 for c in catalog]
    members = db.q("""SELECT member_id FROM member_snapshot TABLESAMPLE SYSTEM (1)
                      WHERE death_date IS NULL OR death_date > '2009-06-30' LIMIT %s""", (n,))
    out = []
    for m in members:
        item = rng.choices(catalog, weights=weights)[0]
        units = 1 if rng.random() > 0.05 else rng.randint(5, 8)
        out.append(engine.decide_prior_auth({"member_id": m["member_id"], "code": item["code"],
                                             "kind": item["kind"], "units": units}))
    return out
