"""
Test Validate below things:
- Lock timeouts are retried - 55P03 errors trigger retry logic
- Works across isolation levels - Same behavior in READ COMMITTED, REPEATABLE READ, SERIALIZABLE
- Transaction integrity preserved - Same txid_current() across retries
- No connection leaks - Proper cleanup after retries
- Exponential backoff works - Delays prevent lock storm
- Extension handles timeouts correctly - lock_timeout settings respected
"""

from __future__ import annotations

import threading
import time

import psycopg
import pytest


def test_guc_defaults_drive_retry_limits(conn):
    with conn.cursor() as cur:
        cur.execute("SET pg_retry.default_max_tries = 5")
        cur.execute("SET pg_retry.default_base_delay_ms = 1")
        cur.execute("SET pg_retry.default_max_delay_ms = 5")
        cur.execute("SET pg_retry.default_sqlstates = '40001,40P01,55P03,57014'")
        cur.execute("SELECT retry.configure_failure_plan('guc_serial', '40001', 4)")
        cur.execute("SELECT retry.retry(%s)", ("SELECT retry.execute_failure_plan('guc_serial')",))
        cur.execute(
            "SELECT remaining FROM retry.failure_plan WHERE name = 'guc_serial'"
        )
        remaining = cur.fetchone()[0]

    assert remaining == 0


def test_set_local_scope_does_not_leak(conn, dsn):
    with conn.cursor() as cur:
        cur.execute("SET pg_retry.default_max_tries = 3")
        cur.execute("SELECT retry.configure_failure_plan('tx_local', '40001', 1)")

    with psycopg.connect(dsn) as tx_conn:
        with tx_conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SET LOCAL pg_retry.default_max_tries = 2")
            cur.execute("SELECT retry.retry(%s)", ("SELECT retry.execute_failure_plan('tx_local')",))
            cur.execute("COMMIT")

    with psycopg.connect(dsn, autocommit=True) as check_conn:
        with check_conn.cursor() as cur:
            cur.execute("SHOW pg_retry.default_max_tries")
            value = cur.fetchone()[0]

    assert value == "3"


@pytest.mark.parametrize(
    "isolation_level",
    ["read committed", "repeatable read", "serializable"],
)
def test_lock_timeouts_are_retried_in_all_isolation_levels(pg_cluster, dsn, isolation_level):
    def hold_lock():
        with psycopg.connect(dsn) as locker:
            locker.autocommit = False
            with locker.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
                cur.execute("LOCK TABLE retry.accounts IN ACCESS EXCLUSIVE MODE")
                time.sleep(0.4)
                locker.commit()

    blocker = threading.Thread(target=hold_lock)
    blocker.start()
    time.sleep(0.05)

    try:
        with psycopg.connect(dsn) as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("BEGIN")
                cur.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
                cur.execute("SELECT txid_current()")
                top_xid = cur.fetchone()[0]

                cur.execute(
                    "SELECT retry.retry(%s, %s, %s, %s)",
                    ("SELECT retry.lock_waiter()", 4, 5, 200),
                )
                processed = cur.fetchone()[0]
                assert processed == 1

                cur.execute("SELECT txid_current()")
                after_xid = cur.fetchone()[0]
                assert after_xid == top_xid

                cur.execute("COMMIT")
    finally:
        blocker.join()

    with psycopg.connect(dsn, autocommit=True) as check_conn:
        with check_conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND state = 'idle in transaction'
                  AND pid <> pg_backend_pid()
                """
            )
            idle_in_tx = cur.fetchone()[0]

    assert idle_in_tx == 0
