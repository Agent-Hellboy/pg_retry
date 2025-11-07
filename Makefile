EXTENSION = pg_retry
MODULE_big = pg_retry
OBJS = pg_retry.o
DATA = sql/pg_retry--1.0.sql
DOCS = README.md

# Regression tests
REGRESS = pg_retry
REGRESS_OPTS = --load-extension=pg_retry

# Allow overriding PG_CONFIG from environment (useful for CI)
PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
