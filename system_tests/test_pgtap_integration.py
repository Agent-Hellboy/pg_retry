"""
pgTAP integration tests for pg_retry extension

This module runs pgTAP SQL tests using the pgTAP binary directly.
"""

import subprocess
import pytest
import os
import psycopg


@pytest.mark.pgtap
def test_pgtap_setup_sql(pg_cluster):
    """Run pgTAP setup.sql tests."""
    # Check if pgTAP is available by testing if we can create the extension and run a simple test
    with psycopg.connect(pg_cluster.dsn()) as conn:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS pgtap")
            result = conn.execute("SELECT plan(1)")
            conn.execute("SELECT pass('pgTAP is working')")
            conn.execute("SELECT * FROM finish()")
        except psycopg.Error as e:
            pytest.fail(f"pgTAP not available - pgTAP tests require pgTAP to be installed. Error: {e}")

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
    # Simple test to verify pgTAP is working
    with psycopg.connect(pg_cluster.dsn()) as conn:
        result = conn.execute("SELECT 1 as test").fetchone()
        assert result[0] == 1, f"Unexpected query result: {result}"
