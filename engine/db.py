"""Postgres access (connection pool) for the decision engine."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from engine.config import PG_DSN

pool = ConnectionPool(PG_DSN, min_size=2, max_size=10, open=False,
                      kwargs={"autocommit": True, "row_factory": dict_row,
                              "options": "-c search_path=decision_engine,synpuf,public"})


def open_pool() -> None:
    pool.open(wait=True)
    with pool.connection() as c:
        c.execute((Path(__file__).parent / "schema.sql").read_text())


@contextmanager
def conn():
    with pool.connection() as c:
        yield c


def q(sql: str, params=None) -> list[dict]:
    with pool.connection() as c:
        return c.execute(sql, params).fetchall()


def execute(sql: str, params=None) -> None:
    """For statements that return no rows (TRUNCATE, UPDATE without RETURNING...)."""
    with pool.connection() as c:
        c.execute(sql, params)


def q1(sql: str, params=None) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


__all__ = ["pool", "open_pool", "conn", "q", "q1", "Jsonb"]
