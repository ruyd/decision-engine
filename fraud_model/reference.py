"""Build reference tables the engine needs at decision time, from 2008-2009 history only.

    uv run python -m fraud_model.reference

Writes data/ref/*.parquet and loads them into Postgres schema decision_engine:
  ref_hcpcs_price      per procedure code: volume, median and p95 line payment
  ref_drg_price        per DRG: volume, median and p95 inpatient payment
  ref_provider_profile per rendering NPI: billing profile used as fraud features
  member_snapshot      per member: 2009 features for the cost model + coverage/death facts
"""
from __future__ import annotations

import time

import duckdb

from cost_model.dataset import CHRONIC
from engine.config import HISTORY_YEARS, LAKE_DB, PG_DSN, REF, SAMPLES, SNAPSHOT_YEAR

S = ",".join(map(str, SAMPLES))
Y = ",".join(map(str, HISTORY_YEARS))
HIGH_EM = ("99215", "99205", "99223", "99233", "99285", "99245", "99255")
EM_PREFIX = "992"   # evaluation & management visit codes

QUERIES = {
    "ref_hcpcs_price": f"""
        SELECT l.hcpcs_cd, count(*) AS n_lines,
               median(l.line_nch_pmt_amt)::DOUBLE AS p50_amt,
               quantile_cont(l.line_nch_pmt_amt, 0.95)::DOUBLE AS p95_amt,
               avg(l.line_nch_pmt_amt)::DOUBLE AS mean_amt
        FROM synpuf.carrier_line l JOIN synpuf.carrier_claim c USING (sample_id, clm_id)
        WHERE l.sample_id IN ({S}) AND year(c.clm_from_dt) IN ({Y}) AND l.hcpcs_cd IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 20""",
    "ref_drg_price": f"""
        SELECT clm_drg_cd AS drg_cd, count(*) AS n_claims,
               median(clm_pmt_amt)::DOUBLE AS p50_amt,
               quantile_cont(clm_pmt_amt, 0.95)::DOUBLE AS p95_amt,
               median(clm_utlztn_day_cnt)::DOUBLE AS p50_days
        FROM synpuf.inpatient_claim
        WHERE sample_id IN ({S}) AND year(clm_from_dt) IN ({Y}) AND clm_drg_cd IS NOT NULL
        GROUP BY 1 HAVING count(*) >= 10""",
    "ref_provider_profile": f"""
        SELECT l.prf_physn_npi AS npi,
               count(DISTINCT l.clm_id)                          AS prov_claims,
               count(*)                                           AS prov_lines,
               count(DISTINCT l.desynpuf_id)                      AS prov_members,
               count(*) / count(DISTINCT l.desynpuf_id)           AS prov_lines_per_member,
               avg(l.line_nch_pmt_amt)::DOUBLE                    AS prov_paid_per_line,
               count(DISTINCT l.hcpcs_cd)                         AS prov_distinct_hcpcs,
               coalesce(sum((l.hcpcs_cd IN {HIGH_EM})::INT)
                 / nullif(sum((l.hcpcs_cd LIKE '{EM_PREFIX}%')::INT), 0), 0)::DOUBLE AS prov_high_em_share,
               avg((l.hcpcs_cd LIKE '8%')::INT)::DOUBLE           AS prov_lab_share
        FROM synpuf.carrier_line l JOIN synpuf.carrier_claim c USING (sample_id, clm_id)
        WHERE l.sample_id IN ({S}) AND year(c.clm_from_dt) IN ({Y}) AND l.prf_physn_npi IS NOT NULL
        GROUP BY 1""",
    "member_snapshot": f"""
        WITH
        rx  AS (SELECT desynpuf_id, sum(tot_rx_cst_amt) AS rx_cost, count(*) AS rx_fills,
                       count(DISTINCT prod_srvc_id) AS rx_distinct_ndc
                FROM synpuf.rx_event WHERE sample_id IN ({S}) AND year(srvc_dt) = {SNAPSHOT_YEAR} GROUP BY 1),
        ip  AS (SELECT desynpuf_id, count(DISTINCT clm_id) AS ip_stays, sum(clm_utlztn_day_cnt) AS ip_days
                FROM synpuf.inpatient_claim WHERE sample_id IN ({S}) AND year(clm_from_dt) = {SNAPSHOT_YEAR} GROUP BY 1),
        op  AS (SELECT desynpuf_id, count(DISTINCT clm_id) AS op_claims
                FROM synpuf.outpatient_claim WHERE sample_id IN ({S}) AND year(clm_from_dt) = {SNAPSHOT_YEAR} GROUP BY 1),
        car AS (SELECT desynpuf_id, count(*) AS car_claims
                FROM synpuf.carrier_claim WHERE sample_id IN ({S}) AND year(clm_from_dt) = {SNAPSHOT_YEAR} GROUP BY 1),
        dx  AS (SELECT desynpuf_id, count(DISTINCT left(icd9_dgns_cd, 3)) AS dx3_distinct
                FROM synpuf.claim_diagnosis WHERE sample_id IN ({S}) AND year(clm_from_dt) = {SNAPSHOT_YEAR} GROUP BY 1),
        prev AS (SELECT desynpuf_id, medreimb_ip + benres_ip + pppymt_ip + medreimb_op + benres_op + pppymt_op
                        + medreimb_car + benres_car + pppymt_car AS medical_cost_prev
                 FROM synpuf.beneficiary_year WHERE sample_id IN ({S}) AND year = {SNAPSHOT_YEAR} - 1)
        SELECT b.sample_id, b.desynpuf_id AS member_id, b.bene_birth_dt AS birth_date, b.bene_death_dt AS death_date,
               {SNAPSHOT_YEAR} - year(b.bene_birth_dt) AS age, b.bene_sex_ident_cd AS sex, b.bene_race_cd AS race,
               b.bene_esrd_ind::INT AS esrd, b.sp_state_code AS state, b.bene_county_cd AS county,
               b.plan_cvrg_mos_num AS partd_months,
               b.bene_hi_cvrage_tot_mons AS parta_months, b.bene_smi_cvrage_tot_mons AS partb_months,
               b.bene_hmo_cvrage_tot_mons AS hmo_months,
               {", ".join(f"b.{c}::INT AS {c}" for c in CHRONIC)},
               {" + ".join(f"b.{c}::INT" for c in CHRONIC)} AS n_chronic,
               (b.medreimb_ip + b.benres_ip + b.pppymt_ip)::DOUBLE    AS ip_cost,
               (b.medreimb_op + b.benres_op + b.pppymt_op)::DOUBLE    AS op_cost,
               (b.medreimb_car + b.benres_car + b.pppymt_car)::DOUBLE AS car_cost,
               coalesce(rx.rx_cost, 0)::DOUBLE AS rx_cost,
               coalesce(ip.ip_stays, 0) AS ip_stays, coalesce(ip.ip_days, 0) AS ip_days,
               coalesce(op.op_claims, 0) AS op_claims, coalesce(car.car_claims, 0) AS car_claims,
               coalesce(rx.rx_fills, 0) AS rx_fills, coalesce(rx.rx_distinct_ndc, 0) AS rx_distinct_ndc,
               coalesce(dx.dx3_distinct, 0) AS dx3_distinct,
               coalesce(prev.medical_cost_prev, 0)::DOUBLE AS medical_cost_prev
        FROM synpuf.beneficiary_year b
        LEFT JOIN rx USING (desynpuf_id) LEFT JOIN ip USING (desynpuf_id) LEFT JOIN op USING (desynpuf_id)
        LEFT JOIN car USING (desynpuf_id) LEFT JOIN dx USING (desynpuf_id) LEFT JOIN prev USING (desynpuf_id)
        WHERE b.sample_id IN ({S}) AND b.year = {SNAPSHOT_YEAR}""",
}

PG_INDEXES = [
    "ALTER TABLE ref_hcpcs_price ADD PRIMARY KEY (hcpcs_cd)",
    "ALTER TABLE ref_drg_price ADD PRIMARY KEY (drg_cd)",
    "ALTER TABLE ref_provider_profile ADD PRIMARY KEY (npi)",
    "ALTER TABLE member_snapshot ADD PRIMARY KEY (member_id)",
]


def main() -> None:
    REF.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()   # in-memory; lake attached read-only, Postgres read-write
    (REF.parent / "tmp").mkdir(exist_ok=True)
    con.execute(f"SET memory_limit='5GB'; SET threads=6; SET preserve_insertion_order=false; "
                f"SET temp_directory='{REF.parent / 'tmp'}';")   # spill big group-bys to disk
    con.execute(f"ATTACH '{LAKE_DB}' AS lake (READ_ONLY); USE lake;")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres)")
    for name, sql in QUERIES.items():
        t0 = time.time()
        out = REF / f"{name}.parquet"
        con.execute(f"COPY ({sql}) TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
        con.execute(f"DROP TABLE IF EXISTS pg.decision_engine.{name}")
        con.execute(f"CREATE TABLE pg.decision_engine.{name} AS SELECT * FROM read_parquet('{out}')")
        n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchall()[0][0]
        print(f"{name:22s} {n:>9,} rows  {time.time() - t0:5.1f}s")
    con.close()
    import psycopg
    with psycopg.connect(PG_DSN, autocommit=True) as pg:
        pg.execute("SET search_path = decision_engine")
        for sql in PG_INDEXES:
            pg.execute(sql)
        for name in QUERIES:
            pg.execute(f"ANALYZE {name}")
    print("loaded into Postgres schema decision_engine")


if __name__ == "__main__":
    main()
