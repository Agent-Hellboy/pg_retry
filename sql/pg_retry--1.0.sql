-- pg_retry extension installation script

-- Create schema for the extension
CREATE SCHEMA retry;

-- Create the retry function
CREATE OR REPLACE FUNCTION retry.retry(
  sql TEXT,                          -- the SQL statement to run (exactly one statement)
  max_tries INT DEFAULT 3,           -- total attempts = 1 + retries; must be >= 1
  base_delay_ms INT DEFAULT 50,      -- initial backoff delay in milliseconds
  max_delay_ms INT DEFAULT 1000,     -- cap for exponential backoff
  retry_sqlstates TEXT[] DEFAULT ARRAY['40001','40P01','55P03','57014']
  -- 40001: serialization_failure
  -- 40P01: deadlock_detected
  -- 55P03: lock_not_available
  -- 57014: query_canceled (e.g., statement_timeout)
) RETURNS INT                       -- number of rows processed/returned by the statement
AS 'pg_retry', 'pg_retry_retry'
LANGUAGE C VOLATILE PARALLEL RESTRICTED;

-- Grant usage to public
GRANT USAGE ON SCHEMA retry TO PUBLIC;
GRANT EXECUTE ON FUNCTION retry.retry(TEXT, INT, INT, INT, TEXT[]) TO PUBLIC;

-- Add comments
COMMENT ON SCHEMA retry IS 'Retry SQL statements on transient errors with exponential backoff';
COMMENT ON FUNCTION retry.retry(TEXT, INT, INT, INT, TEXT[]) IS
'Retries a single SQL statement on transient errors. Returns the number of rows processed/returned by the statement.';
