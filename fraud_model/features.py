"""Claim-level fraud features. ONE implementation used by training, evaluation and live scoring.

A claim is a dict:
  {"claim_id", "member_id", "provider_npi", "service_date": "YYYY-MM-DD",
   "dx_codes": [...], "lines": [{"line_num", "hcpcs", "amount", "dx"}]}
Context (looked up by the caller, from history) is a dict:
  {"member_claims_30d": int, "dup_count": int, "provider": {ref_provider_profile row} | None}
"""
from __future__ import annotations

import math

HIGH_EM = {"99215", "99205", "99223", "99233", "99285", "99245", "99255"}
DEFAULT_P50, DEFAULT_P95 = 20.0, 150.0      # for codes with too little history

FEATURES = [
    "total_paid", "n_lines", "n_distinct_hcpcs", "max_price_ratio", "n_lines_above_p95",
    "high_em_lines", "lab_lines", "n_dx", "member_claims_30d", "dup_count",
    "prov_known", "prov_log_claims", "prov_lines_per_member", "prov_paid_per_line",
    "prov_high_em_share", "prov_lab_share", "prov_distinct_hcpcs",
]

LABELS = {   # human-readable names for explanations
    "total_paid": "Total billed amount",
    "n_lines": "Number of service lines",
    "n_distinct_hcpcs": "Distinct procedure codes",
    "max_price_ratio": "Highest line price vs. code median",
    "n_lines_above_p95": "Lines priced above 95th percentile",
    "high_em_lines": "Highest-level visit codes billed",
    "lab_lines": "Lab/pathology lines",
    "n_dx": "Diagnosis codes on claim",
    "member_claims_30d": "Member's claims in prior 30 days",
    "dup_count": "Identical prior claims (possible duplicate)",
    "prov_known": "Provider has billing history",
    "prov_log_claims": "Provider claim volume (log)",
    "prov_lines_per_member": "Provider lines per patient",
    "prov_paid_per_line": "Provider average paid per line",
    "prov_high_em_share": "Provider share of highest-level visits",
    "prov_lab_share": "Provider share of lab lines",
    "prov_distinct_hcpcs": "Provider distinct procedure codes",
}

# Population medians of provider features, used when the NPI has no history.
PROVIDER_DEFAULTS = {"prov_log_claims": math.log1p(15), "prov_lines_per_member": 2.0,
                     "prov_paid_per_line": 45.0, "prov_high_em_share": 0.0,
                     "prov_lab_share": 0.1, "prov_distinct_hcpcs": 8.0}


def claim_features(claim: dict, ctx: dict, prices: dict[str, tuple[float, float]]) -> dict[str, float]:
    """prices: hcpcs -> (p50, p95) from ref_hcpcs_price."""
    lines = claim["lines"]
    amounts = [float(l["amount"] or 0) for l in lines]
    codes = [l.get("hcpcs") for l in lines]
    ratios, above = [], 0
    for code, amt in zip(codes, amounts):
        p50, p95 = prices.get(code, (DEFAULT_P50, DEFAULT_P95)) if code else (DEFAULT_P50, DEFAULT_P95)
        ratios.append(amt / max(p50, 10.0))
        above += amt > p95
    prov = ctx.get("provider")
    f = {
        "total_paid": sum(amounts),
        "n_lines": len(lines),
        "n_distinct_hcpcs": len({c for c in codes if c}),
        "max_price_ratio": max(ratios) if ratios else 0.0,
        "n_lines_above_p95": above,
        "high_em_lines": sum(c in HIGH_EM for c in codes),
        "lab_lines": sum(bool(c) and c.startswith("8") for c in codes),
        "n_dx": len(claim.get("dx_codes") or []),
        "member_claims_30d": ctx.get("member_claims_30d", 0),
        "dup_count": ctx.get("dup_count", 0),
        "prov_known": int(prov is not None),
    }
    if prov:
        g = lambda k: float(prov.get(k) or 0.0)   # NULL (e.g. no coded lines) -> 0
        f.update({"prov_log_claims": math.log1p(g("prov_claims")),
                  "prov_lines_per_member": g("prov_lines_per_member"),
                  "prov_paid_per_line": g("prov_paid_per_line"),
                  "prov_high_em_share": g("prov_high_em_share"),
                  "prov_lab_share": g("prov_lab_share"),
                  "prov_distinct_hcpcs": g("prov_distinct_hcpcs")})
    else:
        f.update(PROVIDER_DEFAULTS)
    return {k: float(f[k]) for k in FEATURES}


def claim_signature(lines: list[dict]) -> str:
    """Order-independent fingerprint of a claim's procedure codes (for duplicate detection)."""
    return "|".join(sorted(l.get("hcpcs") or "-" for l in lines))
