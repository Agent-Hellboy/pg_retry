BEGIN;
SELECT retry.retry('SELECT retry.pgbench_lock_workload(''pgbench_lock'', 1, 2, 1)', 6, 20, 200);
COMMIT;
