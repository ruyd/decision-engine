"""Synthetic fraud/abuse patterns injected into real claims.

SynPUF has no fraud labels, so we create known-bad claims by mutating real ones. Used to
(1) evaluate the anomaly model and (2) feed the demo simulator. The scenario name is stored
as ground truth so the UI can show what the engine caught.
"""
from __future__ import annotations

import copy
import random

SCENARIOS = {
    "upcoding": "Office/hospital visits billed at the highest complexity level with inflated prices.",
    "price_inflation": "Every line billed at 4-8x the normal price for the code.",
    "unbundling": "Many extra lab tests added to an ordinary visit, each at top-of-range prices.",
    "duplicate": "Exact resubmission of a claim that was already billed.",
    "deceased_member": "Services billed for a member after their date of death.",
}
MODEL_SCENARIOS = ["upcoding", "price_inflation", "unbundling", "duplicate"]
UPCODE = {"99211": "99215", "99212": "99215", "99213": "99215", "99214": "99215",
          "99231": "99233", "99232": "99233", "99201": "99205", "99202": "99205", "99203": "99205",
          "99204": "99205", "99281": "99285", "99282": "99285", "99283": "99285", "99284": "99285"}
LAB_CODES = ["80053", "80061", "85025", "84443", "83036", "82306", "81001", "84153", "82728", "80048",
             "83540", "82607", "84439", "86803", "87086"]


def _r10(x: float) -> float:          # SynPUF amounts are multiples of $10
    return float(max(10, round(x / 10) * 10))


def inject(claim: dict, scenario: str, prices: dict[str, tuple[float, float]], rng: random.Random) -> dict:
    c = copy.deepcopy(claim)
    c["injected"] = scenario
    lines = c["lines"]
    if scenario == "upcoding":
        hit = False
        for l in lines:
            if l.get("hcpcs") in UPCODE:
                l["hcpcs"] = UPCODE[l["hcpcs"]]
                l["amount"] = _r10(max(prices.get(l["hcpcs"], (0, 150))[1], float(l["amount"] or 0)) * rng.uniform(1.8, 3.0))
                hit = True
        if not hit:
            lines.append({"line_num": len(lines) + 1, "hcpcs": "99215", "dx": (c.get("dx_codes") or [None])[0],
                          "amount": _r10(prices.get("99215", (0, 160))[1] * rng.uniform(1.8, 3.0))})
    elif scenario == "price_inflation":
        for l in lines:
            l["amount"] = _r10(float(l["amount"] or 10) * rng.uniform(4, 8))
    elif scenario == "unbundling":
        for code in rng.sample(LAB_CODES, rng.randint(6, 10)):
            lines.append({"line_num": len(lines) + 1, "hcpcs": code, "dx": (c.get("dx_codes") or [None])[0],
                          "amount": _r10(prices.get(code, (10, 80))[1] * rng.uniform(1.0, 1.6))})
    elif scenario == "duplicate":
        pass   # same content; caller resubmits under a new claim id (dup_count picks it up)
    elif scenario == "deceased_member":
        pass   # caller swaps in a member who died before the service date (caught by a rule)
    else:
        raise ValueError(scenario)
    for i, l in enumerate(lines, 1):
        l["line_num"] = i
    return c
