"""
pgTAP integration tests for pg_retry extension

This module runs pgTAP SQL tests using the pgTAP binary directly.
"""

import os
import subprocess

import psycopg
import pytest


def ensure_pgtap_available(pg_cluster):
    """Ensure pgTAP can be created in the target cluster or skip gracefully."""
    with psycopg.connect(pg_cluster.dsn(), autocommit=True) as conn:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS pgtap")
            conn.execute("SELECT plan(1)")
            conn.execute("SELECT pass('pgTAP is working')")
            conn.execute("SELECT * FROM finish()")
        except psycopg.errors.UndefinedFile as exc:
            pytest.skip(f"pgTAP extension is not installed in this environment: {exc}")
        except psycopg.Error as exc:
            pytest.fail(f"pgTAP setup failed for an unexpected reason: {exc}")


@pytest.mark.pgtap
def test_pgtap_setup_sql(pg_cluster):
    """Run pgTAP setup.sql tests."""
    ensure_pgtap_available(pg_cluster)

    # Change to pgtap directory
    old_cwd = os.getcwd()
    pgtap_dir = "system_tests/pgtap"
    assert os.path.exists(pgtap_dir), f"pgTAP test directory not found: {pgtap_dir}"
    try:
        os.chdir(pgtap_dir)

        # Set up environment for run_tests.sh to use the test cluster
        env = pg_cluster.client_env()
        env["PGDATABASE"] = pg_cluster.database
        
        # Run the existing run_tests.sh script
        result = subprocess.run(
            ["./run_tests.sh"],
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout
            env=env
        )

        # Check that pgTAP ran successfully
        assert result.returncode == 0, f"pgTAP tests failed: {result.stderr}"

        # Check that we got expected output
        output = result.stdout + result.stderr
        assert "pgTAP tests completed" in output, f"pgTAP didn't complete properly. Output: {output}"

        # Check for test summary
        assert "Test Results Summary" in output, f"No test results found. Output: {output}"

    finally:
        os.chdir(old_cwd)


@pytest.mark.pgtap
def test_pgtap_basic_functionality(pg_cluster):
    """Test that pgTAP can run basic tests."""
    ensure_pgtap_available(pg_cluster)
    with psycopg.connect(pg_cluster.dsn()) as conn:
        result = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'pgtap'"
        ).fetchone()
        assert result is not None, "pgTAP extension should be installed but is missing"
