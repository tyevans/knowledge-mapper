#!/usr/bin/env bash
# {{ cookiecutter.project_name }} Database Verification Script
#
# Verifies database integrity after restore or for regular health checks.
# Designed for post-restore validation and ongoing database auditing.
#
# Usage:
#   ./scripts/db-verify.sh                          # Run all verifications
#   ./scripts/db-verify.sh --quick                  # Quick connectivity check
#   ./scripts/db-verify.sh --compare backup.sql.gz  # Compare with backup
#   ./scripts/db-verify.sh --json                   # Output results as JSON
#
# Environment Variables:
#   POSTGRES_HOST          - Database host (default: localhost)
#   POSTGRES_PORT          - Database port (default: 5432)
#   POSTGRES_DB            - Database name (default: {{ cookiecutter.postgres_db }})
#   POSTGRES_USER          - Database user (default: {{ cookiecutter.postgres_user }})
#   PGPASSWORD             - Database password (required)
#   BACKUP_DIR             - Backup directory (default: ./backups)
#
# Exit Codes:
#   0 - All verifications passed
#   1 - General error
#   2 - Configuration error
#   3 - Database connection error
#   4 - Critical verification failed
#   5 - Warnings found (non-critical)

set -euo pipefail

# Script metadata
readonly SCRIPT_NAME="db-verify"
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-{{ cookiecutter.postgres_db }}}"
POSTGRES_USER="${POSTGRES_USER:-{{ cookiecutter.postgres_user }}}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"

# Runtime options
QUICK_MODE=false
COMPARE_BACKUP=""
JSON_OUTPUT=false
VERBOSE=false

# Verification counters
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

# Colors for output (disabled if not a terminal or JSON mode)
setup_colors() {
    if [[ -t 1 ]] && [[ "${JSON_OUTPUT}" != "true" ]]; then
        RED='\033[0;31m'
        GREEN='\033[0;32m'
        YELLOW='\033[1;33m'
        BLUE='\033[0;34m'
        BOLD='\033[1m'
        NC='\033[0m'
    else
        RED=''
        GREEN=''
        YELLOW=''
        BLUE=''
        BOLD=''
        NC=''
    fi
}

# Logging functions
log_info() {
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
    fi
}

log_error() {
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${RED}ERROR${NC}] $*" >&2
    fi
}

log_warn() {
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${YELLOW}WARN${NC}] $*"
    fi
}

log_debug() {
    if [[ "${VERBOSE}" == "true" ]] && [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $*"
    fi
}

log_success() {
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${GREEN}SUCCESS${NC}] $*"
    fi
}

# Check result helpers
check_pass() {
    local check_name="$1"
    local details="${2:-}"
    ((CHECKS_PASSED++)) || true
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "  ${GREEN}[PASS]${NC} ${check_name}${details:+: ${details}}"
    fi
}

check_fail() {
    local check_name="$1"
    local details="${2:-}"
    ((CHECKS_FAILED++)) || true
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "  ${RED}[FAIL]${NC} ${check_name}${details:+: ${details}}"
    fi
}

check_warn() {
    local check_name="$1"
    local details="${2:-}"
    ((CHECKS_WARNED++)) || true
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "  ${YELLOW}[WARN]${NC} ${check_name}${details:+: ${details}}"
    fi
}

check_info() {
    local check_name="$1"
    local details="${2:-}"
    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo -e "  ${BLUE}[INFO]${NC} ${check_name}${details:+: ${details}}"
    fi
}

# Print usage information
usage() {
    cat << EOF
Usage: ${SCRIPT_NAME} [OPTIONS]

Verifies database integrity after restore or for regular health checks.

Options:
    --quick             Quick connectivity and basic checks only
    --compare FILE      Compare database state with backup file
    --json              Output results as JSON (for automation)
    --verbose, -v       Enable verbose output
    --help, -h          Show this help message
    --version           Show version information

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, PGPASSWORD

Examples:
    ${SCRIPT_NAME}                          # Full verification
    ${SCRIPT_NAME} --quick                  # Quick health check
    ${SCRIPT_NAME} --compare backup.sql.gz  # Compare with backup
    ${SCRIPT_NAME} --json                   # JSON output for CI/CD

Exit Codes:
    0 - All verifications passed
    1 - General error
    2 - Configuration error
    3 - Database connection error
    4 - Critical verification failed
    5 - Warnings found (non-critical issues)
EOF
}

# Print version information
version() {
    echo "${SCRIPT_NAME} version ${SCRIPT_VERSION}"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick)
                QUICK_MODE=true
                ;;
            --compare)
                shift
                if [[ $# -eq 0 ]]; then
                    log_error "--compare requires a backup file argument"
                    exit 2
                fi
                COMPARE_BACKUP="$1"
                ;;
            --compare=*)
                COMPARE_BACKUP="${1#*=}"
                ;;
            --json)
                JSON_OUTPUT=true
                ;;
            --verbose|-v)
                VERBOSE=true
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            --version)
                version
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 2
                ;;
        esac
        shift
    done
}

# Validate configuration
validate_config() {
    if [[ -z "${PGPASSWORD:-}" ]]; then
        log_error "PGPASSWORD environment variable is required"
        exit 2
    fi

    if ! command -v psql &> /dev/null; then
        log_error "psql is required but not installed"
        exit 2
    fi
}

# Execute SQL query
run_query() {
    local query="$1"
    psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -t -A -c "${query}" 2>/dev/null
}

# Execute SQL query with headers
run_query_formatted() {
    local query="$1"
    psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        -c "${query}" 2>/dev/null
}

# ============================================================================
# Verification Checks
# ============================================================================

# Check database connectivity
verify_connectivity() {
    log_info "Checking database connectivity..."

    # Check with pg_isready
    if command -v pg_isready &> /dev/null; then
        if pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q 2>/dev/null; then
            check_pass "PostgreSQL server accepting connections"
        else
            check_fail "PostgreSQL server not accepting connections"
            return 1
        fi
    fi

    # Verify actual connection
    if run_query "SELECT 1" > /dev/null 2>&1; then
        check_pass "Database connection established"
    else
        check_fail "Cannot execute queries on database"
        return 1
    fi

    # Check database version
    local pg_version
    pg_version="$(run_query "SELECT version();")"
    check_info "PostgreSQL version" "${pg_version%%(*}"

    return 0
}

# Check schema version and migrations
verify_schema_version() {
    log_info "Checking schema version..."

    # Check if schema_version table exists (common pattern)
    local has_schema_version
    has_schema_version="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_version');")"

    if [[ "${has_schema_version}" == "t" ]]; then
        local version
        version="$(run_query "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;" 2>/dev/null || echo "unknown")"
        check_pass "Schema version table exists" "version ${version}"
    else
        # Check for Alembic migrations (common with SQLAlchemy)
        local has_alembic
        has_alembic="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'alembic_version');")"

        if [[ "${has_alembic}" == "t" ]]; then
            local alembic_version
            alembic_version="$(run_query "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo "unknown")"
            check_pass "Alembic migration table exists" "revision ${alembic_version}"
        else
            check_info "No migration tracking table found" "(schema_version or alembic_version)"
        fi
    fi
}

# Check table structure and counts
verify_tables() {
    log_info "Checking tables..."

    # Get table count
    local table_count
    table_count="$(run_query "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';")"

    if [[ "${table_count}" -eq 0 ]]; then
        check_warn "No tables found in public schema"
    else
        check_pass "Tables in public schema" "${table_count}"
    fi

    # List tables with row counts
    if [[ "${VERBOSE}" == "true" ]] && [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo ""
        echo "  Table Row Counts:"
        echo "  -----------------"
        run_query "
            SELECT
                schemaname || '.' || relname as table_name,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC;
        " | while IFS='|' read -r table rows; do
            printf "    %-40s %s rows\n" "${table}" "${rows}"
        done
        echo ""
    fi

    # Check for expected core tables (customize for your application)
    local expected_tables=("tenants" "users")
    for table in "${expected_tables[@]}"; do
        local exists
        exists="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '${table}');")"
        if [[ "${exists}" == "t" ]]; then
            local row_count
            row_count="$(run_query "SELECT count(*) FROM \"${table}\";")"
            check_pass "Table '${table}' exists" "${row_count} rows"
        else
            check_warn "Expected table '${table}' not found"
        fi
    done
}

# Check Row-Level Security policies
verify_rls() {
    log_info "Checking Row-Level Security..."

    # Count RLS policies
    local rls_count
    rls_count="$(run_query "SELECT count(*) FROM pg_policies;")"

    if [[ "${rls_count}" -gt 0 ]]; then
        check_pass "RLS policies configured" "${rls_count} policies"

        # Check RLS is enabled on tables with policies
        local rls_enabled_count
        rls_enabled_count="$(run_query "
            SELECT count(*)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            AND c.relrowsecurity = true;
        ")"
        check_info "Tables with RLS enabled" "${rls_enabled_count}"

        if [[ "${VERBOSE}" == "true" ]] && [[ "${JSON_OUTPUT}" != "true" ]]; then
            echo ""
            echo "  RLS Policies:"
            echo "  -------------"
            run_query "
                SELECT tablename, policyname, cmd, qual IS NOT NULL as has_qual
                FROM pg_policies
                WHERE schemaname = 'public'
                ORDER BY tablename, policyname;
            " | while IFS='|' read -r table policy cmd has_qual; do
                printf "    %-30s %-30s %-10s %s\n" "${table}" "${policy}" "${cmd}" "${has_qual}"
            done
            echo ""
        fi
    else
        check_warn "No RLS policies found" "Multi-tenant security may not be enforced"
    fi
}

# Check indexes
verify_indexes() {
    log_info "Checking indexes..."

    local index_count
    index_count="$(run_query "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';")"

    if [[ "${index_count}" -gt 0 ]]; then
        check_pass "Indexes in public schema" "${index_count}"
    else
        check_warn "No indexes found" "Query performance may be affected"
    fi

    # Check for missing primary keys
    local tables_without_pk
    tables_without_pk="$(run_query "
        SELECT count(*)
        FROM information_schema.tables t
        LEFT JOIN information_schema.table_constraints tc
            ON t.table_schema = tc.table_schema
            AND t.table_name = tc.table_name
            AND tc.constraint_type = 'PRIMARY KEY'
        WHERE t.table_schema = 'public'
        AND t.table_type = 'BASE TABLE'
        AND tc.constraint_name IS NULL;
    ")"

    if [[ "${tables_without_pk}" -gt 0 ]]; then
        check_warn "Tables without primary key" "${tables_without_pk}"
    else
        check_pass "All tables have primary keys"
    fi

    # Check for unused indexes (optional, verbose only)
    if [[ "${VERBOSE}" == "true" ]]; then
        local unused_indexes
        unused_indexes="$(run_query "
            SELECT count(*)
            FROM pg_stat_user_indexes
            WHERE idx_scan = 0 AND idx_tup_read = 0;
        ")"
        if [[ "${unused_indexes}" -gt 0 ]]; then
            check_info "Potentially unused indexes" "${unused_indexes}"
        fi
    fi
}

# Check foreign key integrity
verify_referential_integrity() {
    log_info "Checking referential integrity..."

    # Count foreign keys
    local fk_count
    fk_count="$(run_query "
        SELECT count(*)
        FROM information_schema.table_constraints
        WHERE constraint_type = 'FOREIGN KEY'
        AND table_schema = 'public';
    ")"

    if [[ "${fk_count}" -gt 0 ]]; then
        check_pass "Foreign key constraints" "${fk_count}"
    else
        check_info "No foreign key constraints found"
    fi

    # Check for orphaned tenant references (if tenants table exists)
    local has_tenants
    has_tenants="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tenants');")"

    if [[ "${has_tenants}" == "t" ]]; then
        # Check users table for orphaned tenant references
        local has_users
        has_users="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users');")"

        if [[ "${has_users}" == "t" ]]; then
            # Check if tenant_id column exists in users
            local has_tenant_id
            has_tenant_id="$(run_query "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'tenant_id');")"

            if [[ "${has_tenant_id}" == "t" ]]; then
                local orphaned_users
                orphaned_users="$(run_query "
                    SELECT count(*)
                    FROM users u
                    WHERE u.tenant_id IS NOT NULL
                    AND NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = u.tenant_id);
                " 2>/dev/null || echo "0")"

                if [[ "${orphaned_users}" -gt 0 ]]; then
                    check_fail "Orphaned user records" "${orphaned_users} users with invalid tenant_id"
                else
                    check_pass "No orphaned user records"
                fi
            fi
        fi
    fi
}

# Check database size and bloat
verify_database_size() {
    log_info "Checking database size..."

    # Get database size
    local db_size
    db_size="$(run_query "SELECT pg_size_pretty(pg_database_size(current_database()));")"
    check_info "Database size" "${db_size}"

    # Get total table size
    local table_size
    table_size="$(run_query "SELECT pg_size_pretty(sum(pg_total_relation_size(quote_ident(tablename)::regclass))) FROM pg_tables WHERE schemaname = 'public';")"
    check_info "Total table size (with indexes)" "${table_size}"

    # Check for table bloat (simplified check)
    if [[ "${VERBOSE}" == "true" ]]; then
        local bloat_estimate
        bloat_estimate="$(run_query "
            SELECT count(*)
            FROM pg_stat_user_tables
            WHERE n_dead_tup > n_live_tup * 0.2
            AND n_live_tup > 1000;
        ")"
        if [[ "${bloat_estimate}" -gt 0 ]]; then
            check_warn "Tables with potential bloat" "${bloat_estimate} (consider VACUUM)"
        fi
    fi
}

# Check for common issues
verify_common_issues() {
    log_info "Checking for common issues..."

    # Check for NULL in NOT NULL columns (shouldn't happen, but verify)
    # This is a sanity check that constraints are working

    # Check for sequences
    local sequence_count
    sequence_count="$(run_query "SELECT count(*) FROM pg_sequences WHERE schemaname = 'public';")"
    if [[ "${sequence_count}" -gt 0 ]]; then
        check_pass "Sequences configured" "${sequence_count}"
    fi

    # Check for invalid encoding
    local encoding
    encoding="$(run_query "SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = current_database();")"
    if [[ "${encoding}" == "UTF8" ]]; then
        check_pass "Database encoding" "${encoding}"
    else
        check_warn "Database encoding" "${encoding} (UTF8 recommended)"
    fi

    # Check connection limit
    local max_connections
    max_connections="$(run_query "SHOW max_connections;")"
    local current_connections
    current_connections="$(run_query "SELECT count(*) FROM pg_stat_activity;")"
    check_info "Connections" "${current_connections}/${max_connections}"

    # Check if ANALYZE has been run recently
    local tables_never_analyzed
    tables_never_analyzed="$(run_query "
        SELECT count(*)
        FROM pg_stat_user_tables
        WHERE last_analyze IS NULL AND last_autoanalyze IS NULL;
    ")"
    if [[ "${tables_never_analyzed}" -gt 0 ]]; then
        check_warn "Tables never analyzed" "${tables_never_analyzed} (run ANALYZE)"
    else
        check_pass "All tables have been analyzed"
    fi
}

# Check extensions
verify_extensions() {
    log_info "Checking extensions..."

    local extensions
    extensions="$(run_query "SELECT extname FROM pg_extension WHERE extname != 'plpgsql' ORDER BY extname;")"

    if [[ -n "${extensions}" ]]; then
        local ext_count
        ext_count="$(echo "${extensions}" | wc -l)"
        check_pass "Extensions installed" "${ext_count}"

        if [[ "${VERBOSE}" == "true" ]] && [[ "${JSON_OUTPUT}" != "true" ]]; then
            echo "  Extensions: ${extensions//$'\n'/, }"
        fi
    else
        check_info "No additional extensions installed"
    fi

    # Check for commonly needed extensions
    local has_uuid
    has_uuid="$(run_query "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp');")"
    if [[ "${has_uuid}" == "t" ]]; then
        check_pass "UUID extension available"
    fi
}

# Compare with backup file
compare_with_backup() {
    local backup_file="$1"

    log_info "Comparing database with backup..."

    # Resolve backup file path
    if [[ ! -f "${backup_file}" ]]; then
        if [[ -f "${BACKUP_DIR}/${backup_file}" ]]; then
            backup_file="${BACKUP_DIR}/${backup_file}"
        else
            log_error "Backup file not found: ${backup_file}"
            return 1
        fi
    fi

    # Check backup file is readable
    if ! zcat "${backup_file}" > /dev/null 2>&1; then
        log_error "Cannot read backup file"
        return 1
    fi

    echo ""
    check_info "Comparing with" "$(basename "${backup_file}")"

    # Get tables from backup
    local backup_tables
    backup_tables="$(zcat "${backup_file}" | grep -E '^CREATE TABLE' | \
        sed 's/CREATE TABLE \(IF NOT EXISTS \)\?//' | sed 's/ *(.*//' | tr -d '"' | sort)"

    # Get tables from database
    local db_tables
    db_tables="$(run_query "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")"

    # Compare table lists
    local backup_table_count
    backup_table_count="$(echo "${backup_tables}" | grep -c . || echo 0)"
    local db_table_count
    db_table_count="$(echo "${db_tables}" | grep -c . || echo 0)"

    check_info "Tables in backup" "${backup_table_count}"
    check_info "Tables in database" "${db_table_count}"

    # Find missing tables
    local missing_tables
    missing_tables="$(comm -23 <(echo "${backup_tables}") <(echo "${db_tables}"))"
    if [[ -n "${missing_tables}" ]]; then
        check_warn "Tables in backup but not in database" "$(echo "${missing_tables}" | wc -l)"
        if [[ "${VERBOSE}" == "true" ]]; then
            echo "    Missing: ${missing_tables//$'\n'/, }"
        fi
    fi

    # Find extra tables
    local extra_tables
    extra_tables="$(comm -13 <(echo "${backup_tables}") <(echo "${db_tables}"))"
    if [[ -n "${extra_tables}" ]]; then
        check_info "Tables in database but not in backup" "$(echo "${extra_tables}" | wc -l)"
    fi

    # Compare RLS policies
    local backup_policies
    backup_policies="$(zcat "${backup_file}" | grep -c 'CREATE POLICY' || echo 0)"
    local db_policies
    db_policies="$(run_query "SELECT count(*) FROM pg_policies;")"

    check_info "RLS policies in backup" "${backup_policies}"
    check_info "RLS policies in database" "${db_policies}"

    if [[ "${backup_policies}" -ne "${db_policies}" ]]; then
        check_warn "RLS policy count mismatch" "backup: ${backup_policies}, database: ${db_policies}"
    fi
}

# Generate JSON output
generate_json_output() {
    cat << EOF
{
    "timestamp": "$(date -Iseconds)",
    "database": "${POSTGRES_DB}",
    "host": "${POSTGRES_HOST}",
    "port": ${POSTGRES_PORT},
    "results": {
        "checks_passed": ${CHECKS_PASSED},
        "checks_failed": ${CHECKS_FAILED},
        "checks_warned": ${CHECKS_WARNED},
        "status": "$(if [[ ${CHECKS_FAILED} -gt 0 ]]; then echo "failed"; elif [[ ${CHECKS_WARNED} -gt 0 ]]; then echo "warning"; else echo "passed"; fi)"
    },
    "script_version": "${SCRIPT_VERSION}"
}
EOF
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    parse_args "$@"
    setup_colors
    validate_config

    if [[ "${JSON_OUTPUT}" != "true" ]]; then
        echo ""
        echo "=============================================="
        echo "   {{ cookiecutter.project_name }} Database Verification"
        echo "=============================================="
        echo ""
        echo "Database: ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"
        echo "Mode: $(if [[ "${QUICK_MODE}" == "true" ]]; then echo "Quick"; else echo "Full"; fi)"
        echo ""
    fi

    # Run verifications
    local exit_code=0

    # Always run connectivity check
    if ! verify_connectivity; then
        exit_code=3
        if [[ "${JSON_OUTPUT}" == "true" ]]; then
            generate_json_output
        fi
        exit ${exit_code}
    fi

    if [[ "${QUICK_MODE}" == "true" ]]; then
        # Quick mode: just basic checks
        verify_tables
        verify_rls
    else
        # Full verification
        echo ""
        verify_schema_version
        echo ""
        verify_tables
        echo ""
        verify_rls
        echo ""
        verify_indexes
        echo ""
        verify_referential_integrity
        echo ""
        verify_database_size
        echo ""
        verify_extensions
        echo ""
        verify_common_issues
    fi

    # Compare with backup if specified
    if [[ -n "${COMPARE_BACKUP}" ]]; then
        echo ""
        compare_with_backup "${COMPARE_BACKUP}"
    fi

    # Summary
    if [[ "${JSON_OUTPUT}" == "true" ]]; then
        generate_json_output
    else
        echo ""
        echo "=============================================="
        echo "                  Summary"
        echo "=============================================="
        echo ""
        echo -e "  ${GREEN}Passed:${NC}   ${CHECKS_PASSED}"
        echo -e "  ${YELLOW}Warnings:${NC} ${CHECKS_WARNED}"
        echo -e "  ${RED}Failed:${NC}   ${CHECKS_FAILED}"
        echo ""

        if [[ ${CHECKS_FAILED} -gt 0 ]]; then
            log_error "Verification FAILED - critical issues found"
            exit_code=4
        elif [[ ${CHECKS_WARNED} -gt 0 ]]; then
            log_warn "Verification completed with warnings"
            exit_code=5
        else
            log_success "All verifications passed"
            exit_code=0
        fi
        echo ""
    fi

    exit ${exit_code}
}

main "$@"
