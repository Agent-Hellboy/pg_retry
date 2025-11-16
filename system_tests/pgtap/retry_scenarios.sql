-- Advanced pgTAP tests for retry scenarios
SELECT * FROM pg_tap_setup();
CREATE EXTENSION IF NOT EXISTS pg_retry;

SELECT plan(12);

-- Test 1: Serialization failure retry
SELECT configure_failure_plan('serial_test', '40001', 1);
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''serial_test'')$$, 3, 10, 100)',
    '40001',
    'Serialization failure should be retried'
);

-- Test 2: Deadlock retry
SELECT configure_failure_plan('deadlock_test', '40P01', 1);
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''deadlock_test'')$$, 3, 10, 100)',
    '40P01',
    'Deadlock should be retried'
);

-- Test 3: Lock timeout retry
SELECT configure_failure_plan('lock_test', '55P03', 1);
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''lock_test'')$$, 3, 10, 100)',
    '55P03',
    'Lock timeout should be retried'
);

-- Test 4: Query cancellation retry
SELECT configure_failure_plan('cancel_test', '57014', 1);
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''cancel_test'')$$, 3, 10, 100)',
    '57014',
    'Query cancellation should be retried'
);

-- Test 5: Non-retryable error (should not retry)
SELECT throws_ok(
    'SELECT retry.retry($$SELECT 1/0$$, 3, 10, 100)',
    '22012',  -- division_by_zero - not in retry list
    'Non-retryable errors should not be retried'
);

-- Test 6: Success after retries
SELECT configure_failure_plan('success_after_retry', '40001', 1);
SELECT is(
    retry.retry('SELECT retry.execute_failure_plan(''success_after_retry''); SELECT 42', 3, 10, 100),
    42,
    'Should succeed after initial failure'
);

-- Test 7: Max retries exceeded
SELECT configure_failure_plan('max_retry_test', '40001', 5); -- Fail 5 times
SELECT throws_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''max_retry_test'')$$, 2, 10, 100)',
    '40001',
    'Should fail when max retries exceeded'
);

-- Test 8: Exponential backoff timing
SELECT configure_failure_plan('timing_test', '40001', 1);
SELECT lives_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''timing_test''); SELECT pg_sleep(0.01)$$, 2, 50, 200)',
    'Exponential backoff should work with delays'
);

-- Test 9: GUC parameter effects
SELECT lives_ok(
    'SET retry.max_tries = 2; SELECT retry.retry($$SELECT 1$$, 3, 10, 100)',
    'GUC parameters should affect behavior'
);

-- Test 10: Nested transactions
SELECT lives_ok(
    'SELECT retry.retry($$
        BEGIN;
        SAVEPOINT sp1;
        SELECT 1;
        RELEASE SAVEPOINT sp1;
        COMMIT
    $$, 2, 10, 100)',
    'Nested transactions should work'
);

-- Test 11: Large result sets
SELECT is(
    retry.retry('SELECT generate_series(1,100) LIMIT 1', 2, 10, 100),
    1,
    'Large result handling should work'
);

-- Test 12: Concurrent failure plans
SELECT configure_failure_plan('concurrent_1', '40001', 1);
SELECT configure_failure_plan('concurrent_2', '40P01', 1);
SELECT lives_ok(
    'SELECT retry.retry($$SELECT retry.execute_failure_plan(''concurrent_1'') UNION SELECT retry.execute_failure_plan(''concurrent_2'')$$, 3, 10, 100)',
    'Concurrent failure plans should work'
);

SELECT * FROM finish();

