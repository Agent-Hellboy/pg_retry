EXTENSION    = $(shell python3 -c "import json; print(json.load(open('META.json'))['name'])")

EXTVERSION   = $(shell python3 -c "import json; meta=json.load(open('META.json')); ext=meta['name']; print(meta['provides'][ext]['version'])")

DISTVERSION  = $(shell python3 -c "import json; print(json.load(open('META.json'))['version'])")

DATA 		    = $(wildcard extension_sql/*--*.sql)

TESTS        = $(wildcard test/sql/*.sql)

REGRESS      = $(patsubst test/sql/%.sql,%,$(TESTS))

REGRESS_OPTS = --inputdir=test --load-extension=pg_retry

MODULES      = $(patsubst %.c,%,$(wildcard src/*.c))

PG_CONFIG   ?= pg_config

EXTRA_CLEAN = extension_sql/$(EXTENSION)--$(EXTVERSION).sql

# Additional compiler flags (PGXS provides most flags)
PG_CFLAGS += -DUSE_ASSERT_CHECKING -Wall -Wextra -Werror -Wno-unused-parameter -Wno-sign-compare -std=c11 \
	-Wimplicit-fallthrough -g -O2 -fno-omit-frame-pointer \
	-fstack-protector-strong -D_FORTIFY_SOURCE=3

PGXS := $(shell $(PG_CONFIG) --pgxs)

include $(PGXS)

all: extension_sql/$(EXTENSION)--$(EXTVERSION).sql

extension_sql/$(EXTENSION)--$(EXTVERSION).sql: extension_sql/$(EXTENSION).sql
	cp $< $@

dist: clean all
	mkdir -p $(EXTENSION)-$(DISTVERSION)
	cp -r extension_sql src test META.json Makefile pg_retry.control README.md LICENSE $(EXTENSION)-$(DISTVERSION)/
	# Remove compiled binaries from distribution
	rm -f $(EXTENSION)-$(DISTVERSION)/src/*.o $(EXTENSION)-$(DISTVERSION)/src/*.dylib
	zip -r $(EXTENSION)-$(DISTVERSION).zip $(EXTENSION)-$(DISTVERSION)
	rm -rf $(EXTENSION)-$(DISTVERSION)
