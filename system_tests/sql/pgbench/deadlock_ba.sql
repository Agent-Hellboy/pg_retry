BEGIN;
SELECT retry.retry('SELECT retry.transfer_with_advisory(2, 1, 1, 25, NULL)');
COMMIT;
