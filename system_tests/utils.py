from __future__ import annotations

import random
import time

import psycopg


def run_retry_sql(
    dsn: str,
    sql: str,
    *,
    max_tries: int = 16,
    base_delay_ms: int = 5,
    max_delay_ms: int = 250,
) -> None:
    time.sleep(random.uniform(0, 0.05))
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT retry.retry(%s, %s, %s, %s)",
                (sql, max_tries, base_delay_ms, max_delay_ms),
            )


def fetch_scalar(dsn: str, sql: str):
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return row[0] if row else None
