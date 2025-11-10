EXTENSION    = $(shell grep -m 1 '"name":' META.json | \
               sed -e 's/[[:space:]]*"name":[[:space:]]*"\([^"]*\)",/\1/')

EXTVERSION   = $(shell grep -m 1 '[[:space:]]\{8\}"version":' META.json | \
               sed -e 's/[[:space:]]*"version":[[:space:]]*"\([^"]*\)",\{0,1\}/\1/')

DISTVERSION  = $(shell grep -m 1 '[[:space:]]\{3\}"version":' META.json | \
               sed -e 's/[[:space:]]*"version":[[:space:]]*"\([^"]*\)",\{0,1\}/\1/')

DATA 		    = $(wildcard sql/*--*.sql)

TESTS        = $(wildcard test/sql/*.sql)

REGRESS      = $(patsubst test/sql/%.sql,%,$(TESTS))

REGRESS_OPTS = --inputdir=test --load-extension=pg_retry

MODULES      = $(patsubst %.c,%,$(wildcard src/*.c))

PG_CONFIG   ?= pg_config

PG91         = $(shell $(PG_CONFIG) --version | grep -qE " 8\.| 9\.0" && echo no || echo yes)

EXTRA_CLEAN = sql/$(EXTENSION)--$(EXTVERSION).sql

# Additional compiler flags (PGXS provides most flags)
PG_CFLAGS = -DUSE_ASSERT_CHECKING -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare -std=c11 \
	-Wimplicit-fallthrough -g -O2 -fno-omit-frame-pointer \
	-fstack-protector-strong -D_FORTIFY_SOURCE=3

PGXS := $(shell $(PG_CONFIG) --pgxs)

include $(PGXS)

all: sql/$(EXTENSION)--$(EXTVERSION).sql

sql/$(EXTENSION)--$(EXTVERSION).sql: sql/$(EXTENSION).sql
	cp $< $@

dist:
	git archive --format zip --prefix=$(EXTENSION)-$(DISTVERSION)/ -o $(EXTENSION)-$(DISTVERSION).zip HEAD
