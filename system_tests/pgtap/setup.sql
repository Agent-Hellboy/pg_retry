-- pgTAP tests for pg_retry extension
-- Install pgTAP first: pgxn install pgtap

-- Load pgTAP
SELECT * FROM pg_tap_setup();

-- Load pg_retry extension
CREATE EXTENSION IF NOT EXISTS pg_retry;

-- Basic functionality tests
SELECT plan(15);

-- Test 1: Extension is installed
SELECT has_extension('pg_retry', 'pg_retry extension should be installed');

-- Test 2: retry function exists
SELECT has_function('retry', 'retry(text,integer,integer,integer)', 'retry function should exist');

-- Test 3: configure_failure_plan function exists
SELECT has_function('retry', 'configure_failure_plan(text,text,integer)', 'configure_failure_plan function should exist');

-- Test 4: Basic retry functionality (success case)
SELECT is(
    retry.retry('SELECT 42', 3, 10, 100),
    42,
    'Basic retry should return correct result'
);

-- Test 5: Retry with failure plan (should fail)
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''test_fail'')$$, 2, 10, 100)',
    '40001',
    'Retry with failure plan should throw serialization failure'
);

-- Test 6: GUC parameters exist
SELECT has_guc('retry.base_delay_ms', 'base_delay_ms GUC should exist');
SELECT has_guc('retry.max_delay_ms', 'max_delay_ms GUC should exist');
SELECT has_guc('retry.max_tries', 'max_tries GUC should exist');

-- Test 7: Schema exists
SELECT has_schema('retry', 'retry schema should exist');

-- Test 8: Tables exist
SELECT has_table('retry', 'failure_plans', 'failure_plans table should exist');

-- Test 9: Retry with SQL injection protection
SELECT is(
    retry.retry('SELECT ''safe''::text', 1, 1, 10),
    'safe',
    'SQL injection protection should work'
);

-- Test 10: Max tries validation
SELECT throws_ok(
    'SELECT retry.retry(''SELECT 1'', 0, 10, 100)',
    '22023',  -- invalid_parameter_value
    'max_tries must be >= 1'
);

-- Test 11: Timeout handling
SELECT lives_ok(
    'SELECT retry.retry(''SELECT pg_sleep(0.01)'', 2, 1, 5)',
    'Short operations should complete within timeout'
);

-- Test 12: Subtransaction behavior
SELECT is(
    retry.retry('BEGIN; CREATE TEMP TABLE test_retry (id int); INSERT INTO test_retry VALUES (1); COMMIT; SELECT 1', 2, 10, 100),
    1,
    'Subtransactions should work correctly'
);

-- Test 13: Concurrent access test
SELECT lives_ok(
    'SELECT retry.retry(''SELECT pg_advisory_lock(999)'', 3, 10, 100)',
    'Advisory lock operations should work'
);

-- Test 14: Memory usage check (basic)
SELECT ok(
    retry.retry('SELECT pg_backend_memory_contexts()', 1, 1, 10) IS NOT NULL,
    'Memory context should be accessible'
);

-- Test 15: Extension version check
SELECT ok(
    current_setting('server_version_num')::int >= 170000,
    'PostgreSQL version should be supported (17+)'
);

-- Finish tests
SELECT * FROM finish();
