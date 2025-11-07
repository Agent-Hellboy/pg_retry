EXTENSION = pg_retry
MODULE_big = pg_retry
OBJS = pg_retry.o
DATA = sql/pg_retry--1.0.sql
DOCS = README.md

# Regression tests
REGRESS = pg_retry
REGRESS_OPTS = --load-extension=pg_retry


# Additional compiler flags (PGXS provides most flags)
# Use C11 standard to allow mixed declarations and code
PG_CFLAGS ?= -std=c11
# For strict CI builds: make PG_CFLAGS="-DUSE_ASSERT_CHECKING -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare -std=c11"

PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
