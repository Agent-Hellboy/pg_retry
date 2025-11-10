-- Test pg_retry extension
-- Create test table
CREATE TABLE test_retry_table (id SERIAL PRIMARY KEY, value INT);
-- Test 1: Basic successful SELECT
SELECT retry.retry('SELECT 42');
-- Test 2: Basic successful INSERT
SELECT retry.retry('INSERT INTO test_retry_table (value) VALUES (1)');
-- Test 3: Basic successful UPDATE
SELECT retry.retry('UPDATE test_retry_table SET value = 2 WHERE id = 1');
-- Test 4: Basic successful DELETE
SELECT retry.retry('DELETE FROM test_retry_table WHERE id = 1');
-- Test 5: SELECT with multiple rows
INSERT INTO test_retry_table (value) VALUES (10), (20), (30);
SELECT retry.retry('SELECT * FROM test_retry_table');
-- Test 6: Reject multi-statement SQL
SELECT retry.retry('SELECT 1; SELECT 2');
-- Test 7: Reject transaction control statements
SELECT retry.retry('BEGIN; SELECT 1; COMMIT');
-- Test 8: Reject transaction control (case insensitive)
SELECT retry.retry('begin; select 1; commit');
-- Test 9: Test with custom parameters
SELECT retry.retry('SELECT 123', 2, 10, 100);
-- Test 10: Test invalid max_tries (should fail)
SELECT retry.retry('SELECT 1', 0);
-- Test 11: Test negative delay (should fail)
SELECT retry.retry('SELECT 1', 3, -1);
-- Test 12: Test base_delay > max_delay (should fail)
SELECT retry.retry('SELECT 1', 3, 100, 50);
-- Test 13: Allow semicolons in string literals
SELECT retry.retry('SELECT ''a;b;c''');
-- Test 14: Allow semicolons in JSON values
SELECT retry.retry('SELECT json_build_object(''key'', ''value;with;semicolons'')');
-- Test 15: Allow semicolons in comments
SELECT retry.retry('-- This comment has ; in it
SELECT 42');
-- Test 16: Still reject actual multiple statements
SELECT retry.retry('SELECT 1; SELECT 2');
-- Clean up
DROP TABLE test_retry_table;
