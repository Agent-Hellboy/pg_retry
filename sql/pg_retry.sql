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
) RETURNS INT                       -- number of rows processed/returned by the statement
AS '$libdir/pg_retry'
LANGUAGE C VOLATILE PARALLEL RESTRICTED;

-- Grant usage on the schema
GRANT USAGE ON SCHEMA retry TO PUBLIC;
