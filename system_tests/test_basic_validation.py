#!/usr/bin/env python3
"""
Basic validation tests for pg_retry extension that don't require database connectivity.
These tests validate the extension structure, files, and basic functionality.
"""

import os
import json
import re
import sys
from pathlib import Path


def test_extension_files_exist():
    """Test that all required extension files exist."""
    # Determine if we're running from system_tests directory or root
    if os.path.exists('../extension_sql/pg_retry.sql'):
        # Running from system_tests directory
        base_path = '..'
    else:
        # Running from root directory
        base_path = '.'

    required_files = [
        f'{base_path}/extension_sql/pg_retry.sql',
        f'{base_path}/extension_sql/pg_retry--1.0.0.sql',
        f'{base_path}/src/pg_retry.c',
        f'{base_path}/pg_retry.control',
        f'{base_path}/META.json',
        f'{base_path}/Makefile',
        f'{base_path}/README.md',
        f'{base_path}/LICENSE'
    ]

    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)

    assert len(missing_files) == 0, f"Missing required files: {missing_files}"
    print("✅ All required extension files exist")


def test_control_file():
    """Test that the control file has required fields."""
    base_path = '..' if os.path.exists('../pg_retry.control') else '.'
    with open(f'{base_path}/pg_retry.control', 'r') as f:
        content = f.read()

    required_fields = ['comment', 'default_version', 'module_pathname']
    for field in required_fields:
        assert field in content, f"Control file missing required field: {field}"

    # Check version format
    version_match = re.search(r'default_version\s*=\s*[\'"]?([^\'"\s]+)', content)
    assert version_match, "Could not find version in control file"
    version = version_match.group(1)
    assert version == '1.0.0', f"Control file version should be 1.0.0, got {version}"

    print("✅ Control file validation passed")


def test_meta_json():
    """Test that META.json has required structure."""
    base_path = '..' if os.path.exists('../META.json') else '.'
    with open(f'{base_path}/META.json', 'r') as f:
        meta = json.load(f)

    required_keys = ['name', 'version', 'abstract', 'maintainer', 'license']
    for key in required_keys:
        assert key in meta, f"META.json missing required key: {key}"

    assert meta['name'] == 'pg_retry', f"Expected name 'pg_retry', got {meta['name']}"
    assert meta['version'] == '1.0.0', f"Expected version '1.0.0', got {meta['version']}"

    # Check provides section
    assert 'provides' in meta, "META.json missing provides section"
    assert 'pg_retry' in meta['provides'], "META.json provides section missing pg_retry"

    # Check prereqs
    assert 'prereqs' in meta, "META.json missing prereqs section"
    assert 'runtime' in meta['prereqs'], "META.json missing runtime prereqs"
    assert 'requires' in meta['prereqs']['runtime'], "META.json missing runtime requires"
    assert 'PostgreSQL' in meta['prereqs']['runtime']['requires'], "META.json missing PostgreSQL requirement"

    print("✅ META.json validation passed")


def test_extension_sql():
    """Test that the extension SQL file has correct structure."""
    base_path = '..' if os.path.exists('../extension_sql/pg_retry.sql') else '.'
    with open(f'{base_path}/extension_sql/pg_retry.sql', 'r') as f:
        content = f.read()

    # Check for schema creation
    assert 'CREATE SCHEMA retry' in content, "Extension SQL missing schema creation"

    # Check for function creation
    assert 'CREATE OR REPLACE FUNCTION retry.retry' in content, "Extension SQL missing function creation"

    # Check for library reference
    assert '$libdir/pg_retry' in content, "Extension SQL missing library reference"

    # Check for grants
    assert 'GRANT USAGE ON SCHEMA retry TO PUBLIC' in content, "Extension SQL missing schema grants"

    print("✅ Extension SQL validation passed")


def test_c_source():
    """Test that the C source file has required components."""
    base_path = '..' if os.path.exists('../src/pg_retry.c') else '.'
    with open(f'{base_path}/src/pg_retry.c', 'r') as f:
        content = f.read()

    # Check for required includes
    required_includes = ['postgres.h', 'fmgr.h']
    for include in required_includes:
        assert f'#include "{include}"' in content, f"C source missing required include: {include}"

    # Check for module magic
    assert 'PG_MODULE_MAGIC' in content, "C source missing PG_MODULE_MAGIC"

    # Check for function declarations
    assert 'PG_FUNCTION_INFO_V1(pg_retry_retry)' in content, "C source missing function info"

    # Check for init function
    assert 'void _PG_init(void)' in content, "C source missing _PG_init function"

    print("✅ C source validation passed")


def test_makefile():
    """Test that the Makefile has required components."""
    base_path = '..' if os.path.exists('../Makefile') else '.'
    with open(f'{base_path}/Makefile', 'r') as f:
        content = f.read()

    # Check for required variables (more flexible pattern)
    required_vars = ['EXTENSION', 'EXTVERSION', 'MODULES', 'DATA']
    for var in required_vars:
        # Look for variable assignment with flexible whitespace
        var_pattern = rf'^{var}\s*[:+]?='
        assert re.search(var_pattern, content, re.MULTILINE), f"Makefile missing required variable: {var}"

    # Check for build targets
    assert 'include $(PGXS)' in content, "Makefile missing PGXS include"

    print("✅ Makefile validation passed")


def test_test_structure():
    """Test that the test directory structure is correct."""
    base_path = '..' if os.path.exists('../test/sql/pg_retry.sql') else '.'
    test_files = [
        f'{base_path}/test/sql/pg_retry.sql',
        f'{base_path}/test/expected/pg_retry.out'
    ]

    for test_file in test_files:
        assert os.path.exists(test_file), f"Missing test file: {test_file}"

    print("✅ Test structure validation passed")


def test_compilation():
    """Test that the extension compiles successfully."""
    base_path = '..' if os.path.exists('../src/pg_retry.o') else '.'
    # Check that object files were created
    assert os.path.exists(f'{base_path}/src/pg_retry.o'), "C source not compiled (missing .o file)"
    
    # Check for platform-specific shared library (.so on Linux, .dylib on macOS)
    has_so = os.path.exists(f'{base_path}/src/pg_retry.so')
    has_dylib = os.path.exists(f'{base_path}/src/pg_retry.dylib')
    assert has_so or has_dylib, "Extension not linked (missing .so or .dylib file)"

    print("✅ Compilation validation passed")


if __name__ == '__main__':
    print("🧪 Running pg_retry extension validation tests...")
    print()

    # Run all validation tests
    test_functions = [
        test_extension_files_exist,
        test_control_file,
        test_meta_json,
        test_extension_sql,
        test_c_source,
        test_makefile,
        test_test_structure,
        test_compilation
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1

    print()
    print("📊 Validation Results:")
    print(f"   ✅ Passed: {passed}")
    print(f"   ❌ Failed: {failed}")
    print(f"   📈 Success Rate: {passed}/{passed + failed} ({(passed/(passed+failed)*100):.1f}%)")

    if failed == 0:
        print("🎉 All validation tests passed!")
        sys.exit(0)
    else:
        print("⚠️  Some validation tests failed!")
        sys.exit(1)
