CREATE SCHEMA IF NOT EXISTS retry;

CREATE TABLE IF NOT EXISTS retry.accounts (
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);

INSERT INTO retry.accounts (id, balance)
VALUES
    (1, 1000),
    (2, 1000),
    (3, 1000)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS retry.transfer_history (
    id BIGSERIAL PRIMARY KEY,
    op TEXT NOT NULL,
    first_id INTEGER NOT NULL,
    second_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    txid BIGINT NOT NULL DEFAULT txid_current()
);

DROP VIEW IF EXISTS retry.failure_plan;
DROP TABLE IF EXISTS retry.failure_plan_config;
DO $$
DECLARE
    seq RECORD;
BEGIN
    FOR seq IN
        SELECT schemaname, sequencename
        FROM pg_sequences
        WHERE schemaname = 'retry' AND sequencename LIKE 'failure_plan_seq_%'
    LOOP
        EXECUTE format('DROP SEQUENCE IF EXISTS %I.%I', seq.schemaname, seq.sequencename);
    END LOOP;
END;
$$;

CREATE TABLE retry.failure_plan_config (
    name TEXT PRIMARY KEY,
    sqlstate TEXT NOT NULL,
    failure_count INTEGER NOT NULL,
    seq_schema TEXT NOT NULL DEFAULT 'retry',
    seq_name TEXT NOT NULL
);

CREATE OR REPLACE VIEW retry.failure_plan AS
SELECT
    cfg.name,
    cfg.sqlstate,
    GREATEST(
        cfg.failure_count - LEAST(COALESCE(seq.last_value, 0), cfg.failure_count),
        0
    ) AS remaining
FROM retry.failure_plan_config cfg
LEFT JOIN pg_sequences seq
    ON seq.schemaname = cfg.seq_schema
   AND seq.sequencename = cfg.seq_name;

CREATE OR REPLACE FUNCTION retry.reset_accounts() RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    UPDATE retry.accounts SET balance = 1000;
    TRUNCATE retry.transfer_history;
END;
$$;

CREATE OR REPLACE FUNCTION retry.reset_failure_plans() RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN SELECT seq_schema, seq_name FROM retry.failure_plan_config LOOP
        EXECUTE format('DROP SEQUENCE IF EXISTS %I.%I', rec.seq_schema, rec.seq_name);
    END LOOP;
    DELETE FROM retry.failure_plan_config;
END;
$$;

CREATE OR REPLACE FUNCTION retry._failure_plan_sequence_name(plan_name TEXT)
RETURNS TABLE(seq_schema TEXT, seq_name TEXT) LANGUAGE plpgsql AS $$
DECLARE
    sanitized TEXT;
BEGIN
    sanitized := regexp_replace(plan_name, '[^a-zA-Z0-9_]', '_', 'g');
    seq_schema := 'retry';
    seq_name := format('failure_plan_seq_%s_%s', sanitized, substr(md5(plan_name), 1, 8));
    RETURN NEXT;
    RETURN;
END;
$$;

CREATE OR REPLACE FUNCTION retry.configure_failure_plan(
    plan_name TEXT,
    plan_sqlstate TEXT,
    failure_count INTEGER
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    seq_rec RECORD;
BEGIN
    SELECT * INTO seq_rec FROM retry._failure_plan_sequence_name(plan_name);

    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', seq_rec.seq_schema);
    EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %I.%I MINVALUE 0 START 0 NO CYCLE',
                   seq_rec.seq_schema, seq_rec.seq_name);
    EXECUTE format('ALTER SEQUENCE %I.%I MINVALUE 0 RESTART WITH 0',
                   seq_rec.seq_schema, seq_rec.seq_name);

    INSERT INTO retry.failure_plan_config(name, sqlstate, failure_count, seq_schema, seq_name)
    VALUES (plan_name, plan_sqlstate, failure_count, seq_rec.seq_schema, seq_rec.seq_name)
    ON CONFLICT (name)
    DO UPDATE SET sqlstate = EXCLUDED.sqlstate,
                  failure_count = EXCLUDED.failure_count,
                  seq_schema = EXCLUDED.seq_schema,
                  seq_name = EXCLUDED.seq_name;
END;
$$;

CREATE OR REPLACE FUNCTION retry.execute_failure_plan(plan_name TEXT)
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    plan RECORD;
    attempt BIGINT;
BEGIN
    SELECT * INTO plan
    FROM retry.failure_plan_config
    WHERE name = plan_name;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'unknown failure plan %', plan_name USING ERRCODE = '42883';
    END IF;

    EXECUTE format('SELECT nextval(''%I.%I'')', plan.seq_schema, plan.seq_name) INTO attempt;

    IF attempt < plan.failure_count THEN
        RAISE EXCEPTION 'plan % forcing SQLSTATE %', plan_name, plan.sqlstate
            USING ERRCODE = plan.sqlstate;
    END IF;

    RETURN GREATEST(plan.failure_count - attempt, 0);
END;
$$;

CREATE OR REPLACE FUNCTION retry.transfer_with_advisory(
    first_id INTEGER,
    second_id INTEGER,
    amount INTEGER DEFAULT 1,
    delay_ms INTEGER DEFAULT 10,
    plan_name TEXT DEFAULT NULL
) RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE
    base_sleep DOUBLE PRECISION := GREATEST(delay_ms, 0) / 1000.0;
    jitter DOUBLE PRECISION := (random() - 0.5) * 0.01;
    wait_time DOUBLE PRECISION := GREATEST(base_sleep + jitter, 0);
    pre_lock_delay DOUBLE PRECISION := random() * 0.01;
BEGIN
    IF plan_name IS NOT NULL THEN
        PERFORM retry.execute_failure_plan(plan_name);
    END IF;

    PERFORM pg_sleep(pre_lock_delay);
    PERFORM pg_advisory_xact_lock(first_id);
    PERFORM pg_sleep(wait_time);
    PERFORM pg_advisory_xact_lock(second_id);

    UPDATE retry.accounts
    SET balance = balance - amount
    WHERE id = first_id;

    UPDATE retry.accounts
    SET balance = balance + amount
    WHERE id = second_id;

    INSERT INTO retry.transfer_history(op, first_id, second_id, amount)
    VALUES ('transfer', first_id, second_id, amount);

    RETURN amount;
END;
$$;

CREATE OR REPLACE FUNCTION retry.lock_waiter(target_id INTEGER DEFAULT 1)
RETURNS INTEGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM set_config('lock_timeout', '100ms', true);
    UPDATE retry.accounts SET balance = balance + 1 WHERE id = target_id;
    PERFORM set_config('lock_timeout', '0', true);
    RETURN 1;
END;
$$;

CREATE OR REPLACE FUNCTION retry.pgbench_lock_workload(
    plan_name TEXT,
    first_id INTEGER,
    second_id INTEGER,
    amount INTEGER DEFAULT 1
) RETURNS INTEGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM retry.transfer_with_advisory(first_id, second_id, amount, 15, plan_name);
    RETURN 1;
END;
$$;
