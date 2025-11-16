BEGIN;
SELECT retry.retry('SELECT retry.transfer_with_advisory(1, 2, 1, 25, ''pgbench_deadlock'')');
COMMIT;
