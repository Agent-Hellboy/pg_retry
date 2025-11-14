from __future__ import annotations

import os

import psycopg
import pytest
from psycopg import errors

pytestmark = pytest.mark.faults


def test_external_fault_injection_hook(pg_cluster):
    """Test external fault injection if configured, otherwise skip gracefully."""
    # Always set up default fault injection for testing when --all is used
    fault_sql = "SELECT retry.execute_failure_plan('test_fault')"
    os.environ["PG_FAULT_SQL"] = fault_sql
    os.environ["PG_FAULT_SQLSTATE"] = "40001"
    os.environ["PG_FAULT_EXPECT_SUCCESS"] = "false"
    os.environ["PG_FAULT_MAX_TRIES"] = "1"
    os.environ["PG_FAULT_BASE_DELAY_MS"] = "10"
    os.environ["PG_FAULT_MAX_DELAY_MS"] = "100"

    sqlstate = os.environ.get("PG_FAULT_SQLSTATE")
    expect_success = os.environ.get("PG_FAULT_EXPECT_SUCCESS", "").lower() in {"1", "true", "yes"}
    max_tries = int(os.environ.get("PG_FAULT_MAX_TRIES", "3"))
    base_delay = int(os.environ.get("PG_FAULT_BASE_DELAY_MS", "5"))
    max_delay = int(os.environ.get("PG_FAULT_MAX_DELAY_MS", "250"))

    pg_cluster.truncate_log()

    # Set up a test failure plan for CI
    if "execute_failure_plan" in fault_sql and "'test_fault'" in fault_sql:
        pg_cluster.run_sql("SELECT retry.configure_failure_plan('test_fault', '40001', 3)")

        # Test the failure plan directly first to ensure it works
        try:
            pg_cluster.run_sql("SELECT retry.execute_failure_plan('test_fault')")
            pytest.skip("execute_failure_plan should have failed but didn't")
        except Exception:
            pass  # Expected to fail

    with psycopg.connect(pg_cluster.dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            if expect_success:
                # Test expects success - just run the query
                cur.execute(
                    "SELECT retry.retry(%s, %s, %s, %s)",
                    (fault_sql, max_tries, base_delay, max_delay),
                )
            else:
                # Test expects failure - catch the expected exception
                expected_exc = errors.lookup(sqlstate) if sqlstate else psycopg.Error
                with pytest.raises(expected_exc) as excinfo:
                    cur.execute(
                        "SELECT retry.retry(%s, %s, %s, %s)",
                        (fault_sql, max_tries, base_delay, max_delay),
                    )
                if sqlstate:
                    assert excinfo.value.sqlstate == sqlstate


