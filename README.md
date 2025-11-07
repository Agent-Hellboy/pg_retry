# pg_retry

A PostgreSQL extension that provides retry functionality for SQL statements on transient errors with exponential backoff.

## Overview

`pg_retry` allows you to automatically retry SQL statements that fail due to transient errors such as serialization failures, deadlocks, lock timeouts, or query cancellations. It implements exponential backoff with jitter to avoid thundering herd problems.

## Features

- **Automatic retries** on configurable transient errors
- **Exponential backoff** with configurable base and maximum delays
- **Jitter** to prevent synchronized retries
- **Subtransaction isolation** for each retry attempt
- **Comprehensive validation** to prevent misuse
- **Configurable GUC parameters** for defaults
- **Detailed logging** of retry attempts

## Installation

### Prerequisites

- PostgreSQL 14+
- C compiler and build tools

### Build and Install

```bash
# Clone or download the extension
cd pg_retry

# Build the extension
make

# Install (may require sudo)
make install

# Run tests (optional)
make installcheck
```

### Enable the Extension

```sql
CREATE EXTENSION pg_retry;
```

## Function Signature

```sql
retry.retry(
  sql TEXT,                          -- the SQL statement to run (exactly one statement)
  max_tries INT DEFAULT 3,           -- total attempts = 1 + retries; must be >= 1
  base_delay_ms INT DEFAULT 50,      -- initial backoff delay in milliseconds
  max_delay_ms INT DEFAULT 1000,     -- cap for exponential backoff
  retry_sqlstates TEXT[] DEFAULT ARRAY['40001','40P01','55P03','57014']
) RETURNS INT                       -- number of rows processed/returned by the statement
```

### Retryable SQLSTATEs

By default, the following SQLSTATEs are considered retryable:

- `40001`: serialization_failure
- `40P01`: deadlock_detected
- `55P03`: lock_not_available
- `57014`: query_canceled (e.g., statement_timeout)

## Usage Examples

### Basic Usage

```sql
-- Simple retry with defaults
SELECT retry.retry('UPDATE accounts SET balance = balance - 100 WHERE id = 1');
```

### Custom Retry Parameters

```sql
-- More aggressive retries for critical operations
SELECT retry.retry(
    'INSERT INTO audit_log (event, timestamp) VALUES ($1, NOW())',
    5,        -- max_tries
    100,      -- base_delay_ms
    5000,     -- max_delay_ms
    ARRAY['40001', '40P01', '55P03', '57014', '53300']  -- additional SQLSTATEs
);
```

### Handling Different Statement Types

```sql
-- DML operations return affected rows
SELECT retry.retry('UPDATE users SET last_login = NOW() WHERE id = 123');

-- SELECT returns number of rows returned
SELECT retry.retry('SELECT * FROM large_table WHERE status = $1');

-- DDL/utility operations return 0
SELECT retry.retry('CREATE INDEX CONCURRENTLY ON big_table (column)');
```

## Configuration (GUC Parameters)

You can set default values using PostgreSQL GUC parameters:

```sql
-- Set global defaults
ALTER SYSTEM SET pg_retry.default_max_tries = 5;
ALTER SYSTEM SET pg_retry.default_base_delay_ms = 100;
ALTER SYSTEM SET pg_retry.default_max_delay_ms = 5000;
ALTER SYSTEM SET pg_retry.default_sqlstates = '40001,40P01,55P03,57014,53300';

-- Reload configuration
SELECT pg_reload_conf();
```

## Safety and Validation

The extension includes several safety checks:

### Single Statement Only

Only exactly one SQL statement is allowed per call:

```sql
-- This works
SELECT retry.retry('SELECT 42');

-- This fails
SELECT retry.retry('SELECT 1; SELECT 2');
```

### No Transaction Control

Transaction control statements are prohibited:

```sql
-- These all fail
SELECT retry.retry('BEGIN; SELECT 1; COMMIT');
SELECT retry.retry('SAVEPOINT sp1; SELECT 1; RELEASE sp1');
SELECT retry.retry('ROLLBACK');
```

### Parameter Validation

Input parameters are validated:

```sql
-- These fail
SELECT retry.retry('SELECT 1', 0);           -- max_tries < 1
SELECT retry.retry('SELECT 1', 3, -1);       -- negative delay
SELECT retry.retry('SELECT 1', 3, 1000, 500); -- base > max delay
```

## Retry Behavior

### Exponential Backoff Algorithm

```
delay = min(max_delay_ms, base_delay_ms * (2^(attempt-1)))
jitter = random() * (delay * 0.2)  -- ±20%
final_delay = max(1ms, delay + jitter)
```

### Example Delays (base_delay_ms=50, max_delay_ms=1000)

- Attempt 1: ~50ms ± 10ms
- Attempt 2: ~100ms ± 20ms
- Attempt 3: ~200ms ± 40ms
- Attempt 4: ~400ms ± 80ms
- Attempt 5: ~800ms ± 160ms
- Attempt 6+: ~1000ms ± 200ms

### Logging

Each retry attempt is logged as a WARNING:

```
WARNING: pg_retry: attempt 2/3 failed with SQLSTATE 40001: could not serialize access due to concurrent update
```

## Error Handling

- **Retryable errors**: Automatically retried up to `max_tries`
- **Non-retryable errors**: Immediately rethrown
- **Exhausted retries**: Last error is rethrown with full context

## Performance Considerations

- Each retry runs in a subtransaction
- SPI overhead for statement execution
- Exponential backoff prevents resource exhaustion
- Jitter prevents thundering herd problems

## Limitations

- Only supports single SQL statements
- No support for transaction control
- Cannot retry certain operations (COPY FROM STDIN, large objects, cursors)
- Function is marked `VOLATILE` and `PARALLEL RESTRICTED`

## Testing

Run the regression tests:

```bash
make installcheck
```

## License

Copyright (c) 2025, Prince Roshan

This extension is released under PostgreSQL license terms. See the LICENSE file for the full license text.

## Contributing

1. Fork the repository
2. Make your changes
3. Add tests for new functionality
4. Ensure `make installcheck` passes
5. Submit a pull request
