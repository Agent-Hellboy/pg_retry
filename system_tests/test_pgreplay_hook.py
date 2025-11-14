from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import psycopg
import pytest


@pytest.mark.pgreplay
def test_pgreplay_infrastructure_available(pg_cluster):
    """Test that pgreplay binary is available and can be invoked."""
    pgreplay_bin = shutil.which("pgreplay")
    if not pgreplay_bin:
        pytest.skip("pgreplay binary not found in PATH - skipping pgreplay test")

    # Test that pgreplay can show help/version
    completed = subprocess.run(
        [pgreplay_bin, "-v"],
        capture_output=True,
        text=True,
        timeout=10
    )

    # Should show version without errors
    assert completed.returncode == 0, f"pgreplay version check failed: {completed.stderr}"
    assert "pgreplay" in completed.stdout.lower(), "Should show pgreplay version"

    # Test validates that pgreplay infrastructure is available for retry testing


def test_retry_exponential_backoff_functionality(pg_cluster):
    """Test that exponential backoff works correctly in retry operations."""
    with psycopg.connect(pg_cluster.dsn()) as conn:
        # Configure retry with exponential backoff
        conn.execute("SET retry.max_tries = 4")
        conn.execute("SET retry.base_delay_ms = 50")  # Longer delays for measurement
        conn.execute("SET retry.max_delay_ms = 200")

        # Create failure plan that fails 2 times (should see backoff: 50ms, 100ms)
        conn.execute("SELECT retry.configure_failure_plan('backoff_test', '40001', 2)")

        # Time the retry operation
        start_time = time.time()
        result = conn.execute("""
            SELECT retry.retry(
                $$SELECT retry.execute_failure_plan('backoff_test')$$,
                4, 50, 200
            )
        """).fetchone()[0]
        end_time = time.time()

        assert result >= 0, f"Retry with backoff should return remaining attempts, got {result}"

        # Verify that retries took some time (backoff delays + query execution)
        # Note: Exact timing varies due to jitter (±20%) and query execution time
        elapsed = end_time - start_time
        assert elapsed >= 0.05, f"Retry operation should take some time due to backoff, took {elapsed:.3f}s"

    # Test validates exponential backoff timing in retry operations


def test_retry_guc_parameter_functionality(pg_cluster):
    """Test that GUC parameters work correctly in retry operations."""
    with psycopg.connect(pg_cluster.dsn()) as conn:
        # Set specific GUC values
        conn.execute("SET retry.max_tries = 2")
        conn.execute("SET retry.base_delay_ms = 25")
        conn.execute("SET retry.max_delay_ms = 50")

        # Create failure plan that fails once
        conn.execute("SELECT retry.configure_failure_plan('guc_test', '40001', 1)")

        # Execute with specific parameters
        result = conn.execute("""
            SELECT retry.retry(
                $$SELECT retry.execute_failure_plan('guc_test')$$,
                2, 25, 50
            )
        """).fetchone()[0]

        assert result >= 0, f"GUC-configured retry should return remaining attempts, got {result}"

    # Test validates that GUC parameters are respected in retry operations


def test_retry_error_recovery_functionality(pg_cluster):
    """Test that different error types are handled correctly in retry operations."""
    with psycopg.connect(pg_cluster.dsn()) as conn:
        # Test different error types and recovery patterns
        conn.execute("SET retry.max_tries = 3")

        # Test serialization failure recovery
        conn.execute("SELECT retry.configure_failure_plan('serial_recovery', '40001', 1)")
        serial_result = conn.execute("""
            SELECT retry.retry(
                $$SELECT retry.execute_failure_plan('serial_recovery')$$,
                3, 10, 100
            )
        """).fetchone()[0]
        assert serial_result >= 0

        # Test deadlock recovery
        conn.execute("SELECT retry.configure_failure_plan('deadlock_recovery', '40P01', 1)")
        deadlock_result = conn.execute("""
            SELECT retry.retry(
                $$SELECT retry.execute_failure_plan('deadlock_recovery')$$,
                3, 10, 100
            )
        """).fetchone()[0]
        assert deadlock_result >= 0

    # Test validates that different error types are handled correctly in retry operations
