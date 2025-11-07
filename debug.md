# pg_retry Extension - Debug and Testing Guide

## Compilation Issues and Fixes

### Issue: `pg_config: Command not found`
**Error:**
```
make: pg_config: Command not found
```

**Solution:**
Add PostgreSQL binaries to PATH:
```bash
export PATH="/opt/homebrew/Cellar/postgresql@18/18.0_1/bin:$PATH"
```

**Permanent fix:** Add to your shell profile (`.zshrc`, `.bash_profile`, etc.):
```bash
echo 'export PATH="/opt/homebrew/Cellar/postgresql@18/18.0_1/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Issue: Cached Object Files Causing Stale Errors
**Symptoms:** Compilation errors that don't match current code
**Solution:**
```bash
make clean
make
```

### Issue: C99 Declaration Warning
**Error:**
```
warning: mixing declarations and code is incompatible with standards before C99 [-Wdeclaration-after-statement]
```

**Fix Applied:** Moved variable declarations to top of functions.

## Installation Steps

### Automatic Installation
```bash
export PATH="/opt/homebrew/Cellar/postgresql@18/18.0_1/bin:$PATH"
sudo make install
```

### Manual Installation (if automatic fails)
```bash
# Copy shared library
sudo cp pg_retry.dylib /opt/homebrew/lib/postgresql@18/

# Copy extension files
sudo cp sql/pg_retry--1.0.sql /opt/homebrew/share/postgresql@18/extension/
sudo cp pg_retry.control /opt/homebrew/share/postgresql@18/extension/
```

## Testing Procedures

### 1. Start PostgreSQL Server
```bash
brew services start postgresql@18
# Or manually:
pg_ctl -D /opt/homebrew/var/postgresql@18 start
```

### 2. Run Regression Tests
```bash
export PATH="/opt/homebrew/Cellar/postgresql@18/18.0_1/bin:$PATH"
make installcheck
```

### 3. Manual Testing
```bash
psql postgres
```

```sql
-- Enable extension
CREATE EXTENSION pg_retry;

-- Basic functionality test
SELECT retry.retry('SELECT 42');

-- Test with custom parameters
SELECT retry.retry('SELECT 123', 2, 10, 100);

-- Test error conditions
SELECT retry.retry('SELECT 1', 0);           -- Should fail: max_tries < 1
SELECT retry.retry('SELECT 1', 3, -1);       -- Should fail: negative delay
SELECT retry.retry('SELECT 1', 3, 100, 50); -- Should fail: base > max delay

-- Test SQL validation
SELECT retry.retry('SELECT 1; SELECT 2');    -- Should fail: multi-statement
SELECT retry.retry('BEGIN; SELECT 1');       -- Should fail: transaction control
```

### 4. Test with Concurrent Workloads (Serialization Failures)
```sql
-- Terminal 1: Create test table and start transaction
psql testdb
CREATE TABLE accounts (id INT PRIMARY KEY, balance INT);
INSERT INTO accounts VALUES (1, 1000);
BEGIN;
SELECT retry.retry('UPDATE accounts SET balance = balance - 100 WHERE id = 1');

-- Terminal 2: Try to create serialization conflict
psql testdb
SELECT retry.retry('UPDATE accounts SET balance = balance + 50 WHERE id = 1');
```

## GUC Parameter Testing

### Configure Default Values
```sql
-- Set global defaults
ALTER SYSTEM SET pg_retry.default_max_tries = 5;
ALTER SYSTEM SET pg_retry.default_base_delay_ms = 100;
ALTER SYSTEM SET pg_retry.default_max_delay_ms = 5000;
ALTER SYSTEM SET pg_retry.default_sqlstates = '40001,40P01,55P03,57014,53300';

-- Reload configuration
SELECT pg_reload_conf();

-- Test with defaults
SELECT retry.retry('SELECT 42');  -- Uses configured defaults
```

### Check Current GUC Values
```sql
SHOW pg_retry.default_max_tries;
SHOW pg_retry.default_base_delay_ms;
SHOW pg_retry.default_max_delay_ms;
SHOW pg_retry.default_sqlstates;
```

## Retryable SQLSTATEs

### Default Retryable Errors
- `40001`: serialization_failure
- `40P01`: deadlock_detected
- `55P03`: lock_not_available
- `57014`: query_canceled

### Additional Retryable Errors
- `53300`: too_many_connections
- `57P01`: admin_shutdown
- `XX000`: internal_error (use with caution)

## Performance Testing

### Test Exponential Backoff
```sql
-- Monitor timing of retries
\timing on
SELECT retry.retry('SELECT pg_sleep(0.1)');  -- Force a failure somehow

-- Test different delay configurations
SELECT retry.retry('SELECT 1', 3, 10, 100);   -- Fast retries
SELECT retry.retry('SELECT 1', 5, 100, 2000); -- Slower retries
```

### Subtransaction Overhead
Each retry creates a subtransaction. Monitor with:
```sql
-- Check transaction levels
SELECT pg_current_xact_id_if_assigned(), pg_xact_status(pg_current_xact_id_if_assigned());
```

## Troubleshooting

### PostgreSQL Not Starting
```bash
# Check status
brew services list | grep postgresql

# Check logs
tail -f /opt/homebrew/var/log/postgresql@18.log

# Manual start
pg_ctl -D /opt/homebrew/var/postgresql@18 start
```

### Extension Not Available Error
**Error:** `extension "pg_retry" is not available`
**Cause:** Extension files not installed to PostgreSQL directories
**Solution:**
```bash
# Install extension manually
export PATH="/opt/homebrew/Cellar/postgresql@18/18.0_1/bin:$PATH"
sudo cp pg_retry.dylib /opt/homebrew/lib/postgresql@18/
sudo cp sql/pg_retry--1.0.sql /opt/homebrew/share/postgresql@18/extension/
sudo cp pg_retry.control /opt/homebrew/share/postgresql@18/extension/

# Verify installation
psql postgres -c "SELECT * FROM pg_available_extensions WHERE name = 'pg_retry';"

# If SQL script changes, reinstall:
sudo cp sql/pg_retry--1.0.sql /opt/homebrew/share/postgresql@18/extension/
psql postgres -c "DROP EXTENSION IF EXISTS pg_retry; CREATE EXTENSION pg_retry;"
```

### Schema Name Error
**Error:** `unacceptable schema name "pg_retry"`
**Cause:** PostgreSQL reserves `pg_` prefix for system schemas
**Solution:** Use `retry` schema instead: `retry.retry()` function calls

### Validation Order Fix
**Issue:** Transaction control statements showed "SQL must contain exactly one statement" instead of proper error
**Cause:** Validation checked semicolons before transaction keywords
**Fix:** Reordered validation to check transaction control first, then single statement

### Multi-Statement Detection Fix
**Issue:** SQL like "SELECT 1; SELECT 2" was not being rejected
**Cause:** Semicolon counting logic was flawed - allowed multiple statements with single semicolon
**Fix:** Simplified to reject any SQL containing semicolons (conservative approach)

### Extension Not Loading
```sql
-- Check if extension exists
SELECT * FROM pg_available_extensions WHERE name = 'pg_retry';

-- Check installation location
\dx pg_retry
```

### Connection Issues
```bash
# Test connection
psql -h localhost -p 5432 postgres

# Check if server is listening
netstat -an | grep 5432
```

### Permission Issues
```bash
# Check file permissions
ls -la /opt/homebrew/lib/postgresql@18/pg_retry.dylib
ls -la /opt/homebrew/share/postgresql@18/extension/pg_retry*

# Fix permissions if needed
sudo chmod 755 /opt/homebrew/lib/postgresql@18/pg_retry.dylib
```

## Build System Details

### Compiler Flags Used
- `-Wall -Wmissing-prototypes -Wpointer-arith -Wdeclaration-after-statement`
- `-Werror=vla -Werror=unguarded-availability-new`
- `-Wendif-labels -Wmissing-format-attribute -Wcast-function-type`
- `-Wformat-security -Wmissing-variable-declarations`
- `-fno-strict-aliasing -fwrapv -fexcess-precision=standard`

### PostgreSQL Version Compatibility
- Tested with PostgreSQL 18
- Requires PostgreSQL 14+ for SPI and subtransaction support

### Build Dependencies
- PostgreSQL server development headers
- C compiler (clang/gcc)
- Build tools (make)

## Common Error Patterns

### SPI Connection Failures
```
ERROR: pg_retry: SPI_connect failed
```
**Cause:** SPI already connected or resource exhaustion
**Fix:** Check SPI connection state, ensure proper cleanup

### Subtransaction Issues
```
ERROR: subtransaction already active
```
**Cause:** Nested subtransactions
**Fix:** Ensure proper subtransaction management

### Memory Leaks
**Symptom:** Growing memory usage with retries
**Fix:** Ensure proper `pfree()` calls on allocated memory

## Development Notes

### Code Structure
- `pg_retry.c`: Main extension implementation
- `pg_retry.control`: Extension metadata
- `sql/pg_retry--1.0.sql`: SQL installation script
- `test/`: Regression tests

### Key Functions
- `pg_retry_retry()`: Main retry function
- `is_retryable_sqlstate()`: Check if error should be retried
- `calculate_delay()`: Exponential backoff calculation
- `validate_sql()`: Input validation

### GUC Variables
- `pg_retry.default_max_tries`
- `pg_retry.default_base_delay_ms`
- `pg_retry.default_max_delay_ms`
- `pg_retry.default_sqlstates`

## Testing Checklist

- [ ] Extension compiles without warnings
- [ ] Extension installs successfully
- [ ] Basic SELECT retry works
- [ ] INSERT/UPDATE/DELETE retry works
- [ ] Parameter validation works
- [ ] SQL safety checks work
- [ ] GUC parameters work
- [ ] Serialization failures are retried
- [ ] Non-retryable errors fail immediately
- [ ] Exponential backoff timing is correct
- [ ] Jitter prevents thundering herd
- [ ] Subtransactions isolate retries
- [ ] Memory is properly cleaned up
