-- pg_retry extension installation script

-- Create schema for the extension
CREATE SCHEMA retry;

-- Create the retry function
CREATE OR REPLACE FUNCTION retry.retry(
  sql TEXT,                          -- the SQL statement to run (exactly one statement)
  max_tries INT DEFAULT NULL,        -- total attempts = 1 + retries; must be >= 1
  base_delay_ms INT DEFAULT NULL,    -- initial backoff delay in milliseconds
  max_delay_ms INT DEFAULT NULL,     -- cap for exponential backoff
  retry_sqlstates TEXT[] DEFAULT NULL
) RETURNS INT                       -- number of rows processed/returned by the statement
AS '$libdir/pg_retry', 'pg_retry_retry'
LANGUAGE C VOLATILE PARALLEL RESTRICTED;

-- Grant usage on the schema
GRANT USAGE ON SCHEMA retry TO PUBLIC;
