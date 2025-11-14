"""
pgTAP integration tests for pg_retry extension

This module runs pgTAP SQL tests using the pgTAP binary directly.
"""

import subprocess
import pytest
import os


@pytest.mark.pgtap
def test_pgtap_setup_sql():
    """Run pgTAP setup.sql tests."""
    # Check if pgTAP is available by testing if we can create the extension and run a simple test
    check_result = subprocess.run(
        ["psql", "-c", "CREATE EXTENSION IF NOT EXISTS pgtap; SELECT plan(1); SELECT pass('pgTAP is working'); SELECT * FROM finish();"],
        capture_output=True,
        text=True,
        timeout=10
    )

    assert check_result.returncode == 0, f"pgTAP not available - pgTAP tests require pgTAP to be installed. Error: {check_result.stderr}"

    # Change to pgtap directory
    old_cwd = os.getcwd()
    pgtap_dir = "system_tests/pgtap"
    assert os.path.exists(pgtap_dir), f"pgTAP test directory not found: {pgtap_dir}"
    try:
        os.chdir(pgtap_dir)

        # Run the existing run_tests.sh script
        result = subprocess.run(
            ["./run_tests.sh"],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
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
def test_pgtap_basic_functionality():
    """Test that pgTAP can run basic tests."""
    # Simple test to verify pgTAP is working
    result = subprocess.run(
        ["psql", "-c", "SELECT 1 as test;"],
        capture_output=True,
        text=True,
        timeout=10
    )

    assert result.returncode == 0, f"Basic psql test failed: {result.stderr}"
    assert "1" in result.stdout, f"Unexpected psql output: {result.stdout}"
