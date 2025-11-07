EXTENSION = pg_retry
MODULE_big = pg_retry
OBJS = pg_retry.o
DATA = sql/pg_retry--1.0.sql
DOCS = README.md

# Regression tests
REGRESS = pg_retry
REGRESS_OPTS = --load-extension=pg_retry


# Additional compiler flags (PGXS provides most flags)
# For strict CI builds: make PG_CFLAGS="-DUSE_ASSERT_CHECKING -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare"
PG_CFLAGS ?= -Wall -Wmissing-prototypes -Wpointer-arith -Wdeclaration-after-statement -Werror=vla -Wendif-labels -Wmissing-format-attribute -Wimplicit-fallthrough=3 -Wcast-function-type -Wformat-security -fno-strict-aliasing -fwrapv -fexcess-precision=standard -Wno-format-truncation -Wno-stringop-truncation

PG_CONFIG ?= pg_config
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
