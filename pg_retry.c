#include "postgres.h"
#include "fmgr.h"
#include "miscadmin.h"
#include "utils/guc.h"
#include "executor/spi.h"
#include "utils/builtins.h"
#include "catalog/pg_type.h"
#include "utils/array.h"
#include "utils/lsyscache.h"
#include "access/xact.h"
#include "utils/memutils.h"
#include "utils/errcodes.h"
#include "tcop/tcopprot.h"
#include "parser/parser.h"
#include "nodes/parsenodes.h"
#include "nodes/nodes.h"
#include <math.h>
#include <stdlib.h>
#include <stdio.h>

PG_MODULE_MAGIC;

/* GUC variables */
static int pg_retry_default_max_tries = 3;
static int pg_retry_default_base_delay_ms = 50;
static int pg_retry_default_max_delay_ms = 1000;
/* Default SQLSTATEs to retry on 
40001: serialization_failure
40P01: deadlock_detected
55P03: lock_not_available
57014: query_canceled (e.g., statement_timeout)
*/
static char *pg_retry_default_sqlstates_str = "40001,40P01,55P03,57014";

/* Function declarations */
PG_FUNCTION_INFO_V1(pg_retry_retry);
extern void _PG_init(void);

/* Helper functions */
static bool is_retryable_sqlstate(const char *sqlstate, ArrayType *retry_sqlstates);
static bool contains_transaction_control(List *parsetree_list);
static bool is_single_statement(const char *sql, List **parsed_tree);
static long calculate_delay(int attempt, int base_delay_ms, int max_delay_ms);
static void validate_sql(const char *sql, List **parsed_tree);

/*
 * Check if a SQLSTATE is in the retry list, NOTE: SQLSTATEs are assigned at runtime by PostgreSQL
 */
static bool
is_retryable_sqlstate(const char *sqlstate, ArrayType *retry_sqlstates)
{
    int i;
    int nelems;
    Datum *elements;
    bool *nulls;

    deconstruct_array(retry_sqlstates, TEXTOID, -1, false, 'i', &elements, &nulls, &nelems);

    for (i = 0; i < nelems; i++)
    {
        if (!nulls[i])
        {
            text *elem = DatumGetTextPP(elements[i]);
            char *elem_str = text_to_cstring(elem);

            if (strcmp(sqlstate, elem_str) == 0)
            {
                pfree(elem_str);
                pfree(elements);
                pfree(nulls);
                return true;
            }
            pfree(elem_str);
        }
    }

    pfree(elements);
    pfree(nulls);
    return false;
}

/*
 * Check if parsed statement is a transaction control statement
 */
static bool
contains_transaction_control(List *parsetree_list)
{
    RawStmt *raw_stmt;

    if (parsetree_list == NULL || list_length(parsetree_list) != 1)
        return false;

    raw_stmt = (RawStmt *) linitial(parsetree_list);

    /* Check if the statement is a transaction control command */
    if (IsA(raw_stmt->stmt, TransactionStmt))
        return true;

    return false;
}

/*
 * Check if SQL contains exactly one statement using PostgreSQL parser
 */
static bool
is_single_statement(const char *sql, List **parsed_tree)
{
    List *raw_parsetree_list;

    /* Parse the SQL using PostgreSQL's query parser */
    raw_parsetree_list = pg_parse_query(sql);

    /* Store the parsed tree for later use */
    if (parsed_tree != NULL)
        *parsed_tree = raw_parsetree_list;

    /* Check if we have exactly one statement */
    return (list_length(raw_parsetree_list) == 1);
}

/*
 * Validate SQL input before execution
 *
 * Performs pre-execution validation to ensure SQL safety and correctness:
 * 1. Parse the SQL and verify it contains exactly one statement
 * 2. Check if the statement is a transaction control command (not allowed)
 *
 * The validation uses PostgreSQL's parser to properly handle SQL syntax,
 * including semicolons within string literals, comments, and JSON values.
 *
 * Parameters:
 * - sql: the SQL string to validate
 * - parsed_tree: pointer to store the parsed statement tree for reuse
 *
 * Returns:
 * - void (success) or raises an error if validation fails
 *
 * Errors:
 * - SYNTAX_ERROR: if SQL contains multiple statements or parsing fails
 * - FEATURE_NOT_SUPPORTED: if SQL contains transaction control statements

 *
 * NOTE: We use SPI to execute SQL queries within subtransactions so that
 * errors can be captured and retried without propagating further.
 */
static void
validate_sql(const char *sql, List **parsed_tree)
{
    if (!is_single_statement(sql, parsed_tree))
        ereport(ERROR,
                (errcode(ERRCODE_SYNTAX_ERROR),
                 errmsg("pg_retry: SQL must contain exactly one statement")));

    if (contains_transaction_control(*parsed_tree))
        ereport(ERROR,
                (errcode(ERRCODE_FEATURE_NOT_SUPPORTED),
                 errmsg("pg_retry: transaction control statements are not allowed")));
}

/*
 * Calculate delay with exponential backoff and jitter
 */
static long
calculate_delay(int attempt, int base_delay_ms, int max_delay_ms)
{
    double delay = base_delay_ms * pow(2.0, attempt - 1);
    double jitter;
    delay = Min(delay, (double)max_delay_ms);

    /* Add jitter: ±20% */
    jitter = ((double)rand() / RAND_MAX * delay * 0.4) - delay * 0.2;
    delay += jitter;

    /* Ensure minimum delay of 1ms */
    return Max(1L, (long)delay);
}

/*
 * Main retry function
 */
Datum
pg_retry_retry(PG_FUNCTION_ARGS)
{
    text *sql_text;
    int max_tries;
    int base_delay_ms;
    int max_delay_ms;
    ArrayType *retry_sqlstates;
    char *sql;
    int attempt;
    int spi_result;
    volatile int processed_rows = 0;
    volatile bool success = false;
    volatile ErrorData *last_error = NULL;
    List *parsed_tree = NIL;

    /* Extract arguments */
    if (PG_ARGISNULL(0))
        ereport(ERROR,
                (errcode(ERRCODE_NULL_VALUE_NOT_ALLOWED),
                 errmsg("pg_retry: sql parameter cannot be null")));

    sql_text = PG_GETARG_TEXT_PP(0);
    sql = text_to_cstring(sql_text);

    max_tries = PG_ARGISNULL(1) ? pg_retry_default_max_tries : PG_GETARG_INT32(1);
    base_delay_ms = PG_ARGISNULL(2) ? pg_retry_default_base_delay_ms : PG_GETARG_INT32(2);
    max_delay_ms = PG_ARGISNULL(3) ? pg_retry_default_max_delay_ms : PG_GETARG_INT32(3);

    if (PG_ARGISNULL(4))
    {
        /* Parse default SQLSTATEs */
        Datum sqlstates_datum = DirectFunctionCall1(textin, CStringGetDatum(pg_retry_default_sqlstates_str));
        retry_sqlstates = DatumGetArrayTypeP(
            DirectFunctionCall2(text_to_array, sqlstates_datum, CStringGetTextDatum(",")));
    }
    else
    {
        retry_sqlstates = PG_GETARG_ARRAYTYPE_P(4);
    }

    /* Validate inputs */
    if (max_tries < 1)
        ereport(ERROR,
                (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                 errmsg("pg_retry: max_tries must be >= 1")));

    if (base_delay_ms < 0 || max_delay_ms < 0)
        ereport(ERROR,
                (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                 errmsg("pg_retry: delay parameters must be >= 0")));

    if (base_delay_ms > max_delay_ms)
        ereport(ERROR,
                (errcode(ERRCODE_INVALID_PARAMETER_VALUE),
                 errmsg("pg_retry: base_delay_ms cannot be greater than max_delay_ms")));

    validate_sql(sql, &parsed_tree);

    /* Connect to SPI */
    if (SPI_connect_ext(SPI_OPT_NONATOMIC) != SPI_OK_CONNECT)
        ereport(ERROR,
                (errcode(ERRCODE_CONNECTION_FAILURE),
                 errmsg("pg_retry: SPI_connect failed")));

    /* Retry loop */
    for (attempt = 1; attempt <= max_tries; attempt++)
    {
        PG_TRY();
        {
            /* Start subtransaction */
            BeginInternalSubTransaction(NULL);

            /* Execute the statement */
            spi_result = SPI_execute(sql, false, 0);

            if (spi_result < 0)
            {
                /* SPI error */
                ereport(ERROR,
                        (errcode(ERRCODE_INTERNAL_ERROR),
                         errmsg("pg_retry: SPI_execute failed with code %d", spi_result)));
            }

            processed_rows = SPI_processed;
            success = true;

            /* Commit subtransaction */
            ReleaseCurrentSubTransaction();
        }
        PG_CATCH();
        {
            ErrorData *errdata = CopyErrorData();
            bool should_retry = false;
            FlushErrorState();

            /* Rollback subtransaction */
            RollbackAndReleaseCurrentSubTransaction();

            /* Check if this is a retryable error */
            if (errdata->sqlerrcode != 0)
            {
                const char *sqlstate = unpack_sql_state(errdata->sqlerrcode);

                if (is_retryable_sqlstate(sqlstate, retry_sqlstates))
                {
                    should_retry = true;

                    /* Log retry attempt */
                    ereport(WARNING,
                            (errcode(errdata->sqlerrcode),
                             errmsg("pg_retry: attempt %d/%d failed with SQLSTATE %s: %s",
                                    attempt, max_tries, sqlstate,
                                    errdata->message ? errdata->message : "unknown error")));
                }
            }

            if (!should_retry || attempt == max_tries)
            {
                /* Either not retryable or exhausted attempts - save error for rethrow */
                if (last_error)
                    FreeErrorData((ErrorData *)last_error);
                last_error = errdata;
            }
            else
            {
                /* Retry after delay */
                FreeErrorData(errdata);

                if (attempt < max_tries)
                {
                    long delay_ms = calculate_delay(attempt, base_delay_ms, max_delay_ms);
                    pg_usleep(delay_ms * 1000L);
                    CHECK_FOR_INTERRUPTS();
                }
            }
        }
        PG_END_TRY();

        if (success)
            break;
    }

    /* Disconnect from SPI */
    SPI_finish();

    /* Handle final result */
    if (success)
    {
        pfree(sql);
        PG_RETURN_INT32(processed_rows);
    }
    else
    {
        /* Rethrow the last error */
        if (last_error)
        {
            ReThrowError((ErrorData *)last_error);
        }
        else
        {
            ereport(ERROR,
                    (errcode(ERRCODE_INTERNAL_ERROR),
                     errmsg("pg_retry: all retry attempts failed")));
        }
    }

    /* Should never reach here */
    PG_RETURN_NULL();
}

/*
 * Module initialization
 */
void
_PG_init(void)
{
    /* Register GUC variables */
    DefineCustomIntVariable("pg_retry.default_max_tries",
                           "Default maximum number of retry attempts",
                           NULL,
                           &pg_retry_default_max_tries,
                           3,
                           1,
                           INT_MAX,
                           PGC_SUSET,
                           0,
                           NULL,
                           NULL,
                           NULL);

    DefineCustomIntVariable("pg_retry.default_base_delay_ms",
                           "Default base delay in milliseconds for exponential backoff",
                           NULL,
                           &pg_retry_default_base_delay_ms,
                           50,
                           0,
                           INT_MAX,
                           PGC_SUSET,
                           0,
                           NULL,
                           NULL,
                           NULL);

    DefineCustomIntVariable("pg_retry.default_max_delay_ms",
                           "Default maximum delay in milliseconds for exponential backoff",
                           NULL,
                           &pg_retry_default_max_delay_ms,
                           1000,
                           0,
                           INT_MAX,
                           PGC_SUSET,
                           0,
                           NULL,
                           NULL,
                           NULL);

    DefineCustomStringVariable("pg_retry.default_sqlstates",
                              "Default comma-separated list of SQLSTATEs to retry on",
                              NULL,
                              &pg_retry_default_sqlstates_str,
                              "40001,40P01,55P03,57014",
                              PGC_SUSET,
                              0,
                              NULL,
                              NULL,
                              NULL);
}
