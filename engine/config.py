"""Shared settings for the decision engine (backend, training scripts, simulator)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REF = DATA / "ref"
LAKE_DB = Path.home() / "sources" / "medical-dw" / "data" / "lake.duckdb"

PG_DSN = os.environ.get(
    "DE_PG_DSN",
    "host=localhost port=55433 dbname=medical_dw user=decision_engine password=decision_engine",
)
MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5050")
MLFLOW_UI = os.environ.get("MLFLOW_UI", "http://localhost:5050")

COMPANY = "Ridgeline Health Plan"   # fictional insurer for the demo

# The engine's "world": history = 2008-2009 claims (samples 1-5 in Postgres),
# incoming claims are replayed from 2010, member risk uses 2009 as the base year.
SAMPLES = (1, 2, 3, 4, 5)
HISTORY_YEARS = (2008, 2009)
SNAPSHOT_YEAR = 2009
