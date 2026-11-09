"""Build the next-year cost dataset from the shared SynPUF lake.

One row per beneficiary per base year t:
  features  = who they are + what happened to them in year t
  target    = total cost of care in year t+1 (Medicare paid + beneficiary paid
              + other primary payer, for inpatient/outpatient/carrier, + Part D drug cost)

Splits are by time, never random:
  train = base year 2008 (predict 2009)
  test  = base year 2009 (predict 2010)

    uv run python -m cost_model.dataset          # writes data/next_year_cost.parquet
"""
from __future__ import annotations

import time
from pathlib import Path

import duckdb

LAKE_DB = Path.home() / "sources" / "medical-dw" / "data" / "lake.duckdb"
OUT = Path(__file__).resolve().parent.parent / "data" / "next_year_cost.parquet"

CHRONIC = ["sp_alzhdmta", "sp_chf", "sp_chrnkidn", "sp_cncr", "sp_copd", "sp_depressn",
           "sp_diabetes", "sp_ischmcht", "sp_osteoprs", "sp_ra_oa", "sp_strketia"]

SQL = f"""
WITH
rx  AS (SELECT desynpuf_id, year(srvc_dt) AS yr, sum(tot_rx_cst_amt) AS rx_cost,
               count(*) AS rx_fills, count(DISTINCT prod_srvc_id) AS rx_distinct_ndc
        FROM synpuf.rx_event GROUP BY ALL),
ip  AS (SELECT desynpuf_id, year(clm_from_dt) AS yr, count(DISTINCT clm_id) AS ip_stays,
               sum(clm_utlztn_day_cnt) AS ip_days
        FROM synpuf.inpatient_claim GROUP BY ALL),
op  AS (SELECT desynpuf_id, year(clm_from_dt) AS yr, count(DISTINCT clm_id) AS op_claims
        FROM synpuf.outpatient_claim GROUP BY ALL),
car AS (SELECT desynpuf_id, year(clm_from_dt) AS yr, count(*) AS car_claims
        FROM synpuf.carrier_claim GROUP BY ALL),
dx  AS (SELECT desynpuf_id, year(clm_from_dt) AS yr, count(DISTINCT left(icd9_dgns_cd, 3)) AS dx3_distinct
        FROM synpuf.claim_diagnosis GROUP BY ALL)
SELECT
    cur.sample_id,
    cur.desynpuf_id,
    cur.year                                           AS base_year,
    CASE cur.year WHEN 2008 THEN 'train' ELSE 'test' END AS split,
    -- demographics
    cur.year - year(cur.bene_birth_dt)                 AS age,
    cur.bene_sex_ident_cd                              AS sex,
    cur.bene_race_cd                                   AS race,
    cur.bene_esrd_ind::INT                             AS esrd,
    cur.sp_state_code                                  AS state,
    cur.plan_cvrg_mos_num                              AS partd_months,
    -- chronic conditions in year t
    {", ".join(f"cur.{c}::INT AS {c}" for c in CHRONIC)},
    {" + ".join(f"cur.{c}::INT" for c in CHRONIC)}     AS n_chronic,
    -- cost in year t
    cur.medreimb_ip + cur.benres_ip + cur.pppymt_ip    AS ip_cost,
    cur.medreimb_op + cur.benres_op + cur.pppymt_op    AS op_cost,
    cur.medreimb_car + cur.benres_car + cur.pppymt_car AS car_cost,
    coalesce(rx.rx_cost, 0)                            AS rx_cost,
    -- utilization in year t
    coalesce(ip.ip_stays, 0)        AS ip_stays,
    coalesce(ip.ip_days, 0)         AS ip_days,
    coalesce(op.op_claims, 0)       AS op_claims,
    coalesce(car.car_claims, 0)     AS car_claims,
    coalesce(rx.rx_fills, 0)        AS rx_fills,
    coalesce(rx.rx_distinct_ndc, 0) AS rx_distinct_ndc,
    coalesce(dx.dx3_distinct, 0)    AS dx3_distinct,
    -- TARGET: total cost in year t+1
    nxt.medreimb_ip + nxt.benres_ip + nxt.pppymt_ip
      + nxt.medreimb_op + nxt.benres_op + nxt.pppymt_op
      + nxt.medreimb_car + nxt.benres_car + nxt.pppymt_car
      + coalesce(rxn.rx_cost, 0)                       AS y_cost_next,
    (nxt.bene_death_dt IS NOT NULL)::INT               AS died_next   -- info only, not a feature
FROM synpuf.beneficiary_year cur
JOIN synpuf.beneficiary_year nxt
  ON nxt.desynpuf_id = cur.desynpuf_id AND nxt.year = cur.year + 1
LEFT JOIN rx  ON rx.desynpuf_id  = cur.desynpuf_id AND rx.yr  = cur.year
LEFT JOIN rx rxn ON rxn.desynpuf_id = cur.desynpuf_id AND rxn.yr = cur.year + 1
LEFT JOIN ip  ON ip.desynpuf_id  = cur.desynpuf_id AND ip.yr  = cur.year
LEFT JOIN op  ON op.desynpuf_id  = cur.desynpuf_id AND op.yr  = cur.year
LEFT JOIN car ON car.desynpuf_id = cur.desynpuf_id AND car.yr = cur.year
LEFT JOIN dx  ON dx.desynpuf_id  = cur.desynpuf_id AND dx.yr  = cur.year
WHERE cur.year IN (2008, 2009)
  -- full-year traditional Medicare (Part A + B, no HMO) so claims capture all their care
  AND cur.bene_hi_cvrage_tot_mons = 12
  AND cur.bene_smi_cvrage_tot_mons = 12
  AND cur.bene_hmo_cvrage_tot_mons = 0
  -- alive at the end of the base year
  AND (cur.bene_death_dt IS NULL OR cur.bene_death_dt > make_date(cur.year, 12, 31))
"""


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(LAKE_DB), read_only=True)
    con.execute("SET memory_limit='6GB'; SET preserve_insertion_order=false;")
    t0 = time.time()
    con.execute(f"COPY ({SQL}) TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)")
    stats = con.execute(f"""SELECT split, count(*), round(avg(y_cost_next)), round(median(y_cost_next)),
                                   round(avg((y_cost_next = 0)::INT) * 100, 1), sum((y_cost_next < 0)::INT)
                            FROM '{OUT}' GROUP BY 1 ORDER BY 1 DESC""").fetchall()
    print(f"wrote {OUT} in {time.time() - t0:.1f}s")
    print(f"{'split':6s} {'rows':>10s} {'mean $':>8s} {'median $':>9s} {'% zero':>7s} {'negative':>9s}")
    for s, n, mean, med, zero, neg in stats:
        print(f"{s:6s} {n:>10,} {mean:>8,.0f} {med:>9,.0f} {zero:>7} {neg:>9,}")
    return OUT


if __name__ == "__main__":
    build()
