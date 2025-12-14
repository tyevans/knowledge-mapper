#!/usr/bin/env bash
# {{ cookiecutter.project_name }} Database Restore Script
#
# Restores PostgreSQL database from pg_dump backup files created by db-backup.sh.
# Includes safety checks, verification, and rollback procedures.
#
# Usage:
#   ./scripts/db-restore.sh backup_file.sql.gz              # Restore from file
#   ./scripts/db-restore.sh --list                          # List available backups
#   ./scripts/db-restore.sh --latest                        # Restore most recent backup
#   ./scripts/db-restore.sh --from-s3 backup_file.sql.gz    # Restore from S3
#   ./scripts/db-restore.sh --dry-run backup_file.sql.gz    # Preview without restoring
#   ./scripts/db-restore.sh --schema-only backup_file.sql.gz # Restore schema only
#
# Environment Variables:
#   POSTGRES_HOST          - Database host (default: localhost)
#   POSTGRES_PORT          - Database port (default: 5432)
#   POSTGRES_DB            - Database name (default: {{ cookiecutter.postgres_db }})
#   POSTGRES_USER          - Database user (default: {{ cookiecutter.postgres_user }})
#   PGPASSWORD             - Database password (required)
#   BACKUP_DIR             - Backup directory (default: ./backups)
#   BACKUP_S3_BUCKET       - S3 bucket for remote backups (optional)
#   BACKUP_S3_PREFIX       - S3 prefix (default: backups/)
#   BACKUP_S3_ENDPOINT     - S3-compatible endpoint URL (optional, for Minio)
#   RESTORE_SKIP_CONFIRM   - Skip confirmation prompts (default: false)
#   RESTORE_PRE_BACKUP     - Create pre-restore backup (default: true)
#
# Exit Codes:
#   0 - Success
#   1 - General error
#   2 - Configuration error
#   3 - Database connection error
#   4 - Backup file error
#   5 - Restore error
#   6 - Verification error
#   7 - User cancelled

set -euo pipefail

# Script metadata
readonly SCRIPT_NAME="db-restore"
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-{{ cookiecutter.postgres_db }}}"
POSTGRES_USER="${POSTGRES_USER:-{{ cookiecutter.postgres_user }}}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-backups/}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
RESTORE_SKIP_CONFIRM="${RESTORE_SKIP_CONFIRM:-false}"
RESTORE_PRE_BACKUP="${RESTORE_PRE_BACKUP:-true}"

# Runtime options
BACKUP_FILE=""
DRY_RUN=false
LIST_BACKUPS=false
USE_LATEST=false
FROM_S3=false
SCHEMA_ONLY=false
DATA_ONLY=false
DROP_EXISTING=false
VERBOSE=false
TARGET_DB=""  # If empty, uses POSTGRES_DB

# Temp files tracking for cleanup
TEMP_FILES=()

# Colors for output (disabled if not a terminal)
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    BOLD=''
    NC=''
fi

# Logging functions
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_error() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${RED}ERROR${NC}] $*" >&2
}

log_warn() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${YELLOW}WARN${NC}] $*"
}

log_debug() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $*"
    fi
}

log_success() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] [${GREEN}SUCCESS${NC}] $*"
}

# Cleanup function for temp files
cleanup() {
    local exit_code=$?
    for temp_file in "${TEMP_FILES[@]:-}"; do
        if [[ -f "${temp_file}" ]]; then
            rm -f "${temp_file}"
            log_debug "Cleaned up temp file: ${temp_file}"
        fi
    done
    exit ${exit_code}
}
trap cleanup EXIT

# Print usage information
usage() {
    cat << EOF
Usage: ${SCRIPT_NAME} [OPTIONS] [BACKUP_FILE]

Restores PostgreSQL database from backup files created by db-backup.sh.

Options:
    --list              List available backup files (local and S3)
    --latest            Restore from most recent backup
    --from-s3           Download and restore from S3
    --dry-run           Preview restore without executing
    --schema-only       Restore schema only (no data)
    --data-only         Restore data only (no schema changes)
    --drop              Drop existing objects before restore
    --target-db=NAME    Restore to a different database name
    --skip-confirm      Skip confirmation prompts
    --no-pre-backup     Skip creating pre-restore backup
    --verbose, -v       Enable verbose output
    --help, -h          Show this help message
    --version           Show version information

Arguments:
    BACKUP_FILE         Path to backup file (.sql.gz) or filename in BACKUP_DIR

Examples:
    ${SCRIPT_NAME} --list                         # List available backups
    ${SCRIPT_NAME} --latest                       # Restore most recent backup
    ${SCRIPT_NAME} mydb_daily_20240101.sql.gz     # Restore specific backup
    ${SCRIPT_NAME} --from-s3 --latest             # Restore latest from S3
    ${SCRIPT_NAME} --dry-run backup.sql.gz        # Preview restore
    ${SCRIPT_NAME} --schema-only --latest         # Restore only schema
    ${SCRIPT_NAME} --target-db=mydb_test latest   # Restore to test database

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, PGPASSWORD
    BACKUP_DIR, BACKUP_S3_BUCKET, BACKUP_S3_PREFIX, BACKUP_S3_ENDPOINT
    RESTORE_SKIP_CONFIRM, RESTORE_PRE_BACKUP

Exit Codes:
    0 - Success
    1 - General error
    2 - Configuration error
    3 - Database connection error
    4 - Backup file error
    5 - Restore error
    6 - Verification error
    7 - User cancelled
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
            --list)
                LIST_BACKUPS=true
                ;;
            --latest)
                USE_LATEST=true
                ;;
            --from-s3)
                FROM_S3=true
                ;;
            --dry-run)
                DRY_RUN=true
                ;;
            --schema-only)
                SCHEMA_ONLY=true
                ;;
            --data-only)
                DATA_ONLY=true
                ;;
            --drop)
                DROP_EXISTING=true
                ;;
            --target-db=*)
                TARGET_DB="${1#*=}"
                ;;
            --skip-confirm)
                RESTORE_SKIP_CONFIRM=true
                ;;
            --no-pre-backup)
                RESTORE_PRE_BACKUP=false
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
            -*)
                log_error "Unknown option: $1"
                usage
                exit 2
                ;;
            *)
                BACKUP_FILE="$1"
                ;;
        esac
        shift
    done

    # Validate conflicting options
    if [[ "${SCHEMA_ONLY}" == "true" && "${DATA_ONLY}" == "true" ]]; then
        log_error "Cannot use --schema-only and --data-only together"
        exit 2
    fi

    # Set target database
    if [[ -z "${TARGET_DB}" ]]; then
        TARGET_DB="${POSTGRES_DB}"
    fi
}

# Validate configuration
validate_config() {
    log_info "Validating configuration..."

    # Check required password
    if [[ -z "${PGPASSWORD:-}" ]]; then
        log_error "PGPASSWORD environment variable is required"
        log_error "Set it with: export PGPASSWORD=your_password"
        exit 2
    fi

    # Check backup directory exists (for local restores)
    if [[ ! -d "${BACKUP_DIR}" && "${FROM_S3}" != "true" && "${LIST_BACKUPS}" != "true" ]]; then
        log_error "Backup directory does not exist: ${BACKUP_DIR}"
        log_error "Create it with: mkdir -p ${BACKUP_DIR}"
        exit 2
    fi

    # Check for required tools
    local missing_tools=()

    if ! command -v psql &> /dev/null; then
        missing_tools+=("psql (PostgreSQL client)")
    fi

    if ! command -v zcat &> /dev/null; then
        missing_tools+=("zcat (gzip utilities)")
    fi

    if ! command -v sha256sum &> /dev/null; then
        missing_tools+=("sha256sum (coreutils)")
    fi

    if [[ "${FROM_S3}" == "true" ]] && ! command -v aws &> /dev/null; then
        missing_tools+=("aws (AWS CLI)")
    fi

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Required tools not found:"
        for tool in "${missing_tools[@]}"; do
            log_error "  - ${tool}"
        done
        exit 2
    fi

    log_debug "Configuration validated successfully"
    log_debug "  POSTGRES_HOST: ${POSTGRES_HOST}"
    log_debug "  POSTGRES_PORT: ${POSTGRES_PORT}"
    log_debug "  POSTGRES_DB: ${POSTGRES_DB}"
    log_debug "  TARGET_DB: ${TARGET_DB}"
    log_debug "  BACKUP_DIR: ${BACKUP_DIR}"
}

# Test database connection
test_connection() {
    log_info "Testing database connection..."

    if command -v pg_isready &> /dev/null; then
        if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" -q 2>/dev/null; then
            # Try connecting to postgres database if target doesn't exist yet
            if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -q 2>/dev/null; then
                log_error "Cannot connect to PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}"
                exit 3
            fi
        fi
    fi

    # Verify we can actually connect
    if ! psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" -c "SELECT 1" > /dev/null 2>&1; then
        log_error "Database connection test failed"
        log_error "Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
        log_error "User: ${POSTGRES_USER}"
        exit 3
    fi

    log_debug "Database connection successful"
}

# List available backups (local and S3)
list_backups() {
    echo ""
    echo "=============================================="
    echo "         Available Database Backups"
    echo "=============================================="
    echo ""

    # List local backups
    if [[ -d "${BACKUP_DIR}" ]]; then
        log_info "Local backups in ${BACKUP_DIR}:"
        echo ""

        local count=0
        while IFS= read -r -d '' file; do
            local filename
            filename="$(basename "${file}")"
            local size
            size="$(du -h "${file}" | cut -f1)"
            local date
            date="$(stat -c '%y' "${file}" 2>/dev/null | cut -d'.' -f1 || stat -f "%Sm" "${file}" 2>/dev/null || echo "unknown")"

            # Check for checksum file
            local checksum_status=" "
            if [[ -f "${file}.sha256" ]]; then
                checksum_status="[checksum]"
            fi

            printf "  %-50s %8s  %s %s\n" "${filename}" "${size}" "${date}" "${checksum_status}"
            ((count++)) || true
        done < <(find "${BACKUP_DIR}" -name "*.sql.gz" -type f -print0 2>/dev/null | sort -rz)

        echo ""
        if [[ ${count} -eq 0 ]]; then
            log_warn "No local backups found"
        else
            log_info "Total: ${count} local backup(s)"
        fi
    else
        log_warn "Local backup directory does not exist: ${BACKUP_DIR}"
    fi

    # List S3 backups if configured
    if [[ -n "${BACKUP_S3_BUCKET}" ]]; then
        echo ""
        log_info "S3 backups (s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}):"
        echo ""

        local aws_opts=()
        if [[ -n "${BACKUP_S3_ENDPOINT}" ]]; then
            aws_opts+=(--endpoint-url "${BACKUP_S3_ENDPOINT}")
        fi

        if aws "${aws_opts[@]}" s3 ls "s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}" --recursive 2>/dev/null | grep '\.sql\.gz$' | while read -r line; do
            echo "  ${line}"
        done; then
            :
        else
            log_warn "Cannot access S3 bucket or no backups found"
        fi
    fi

    echo ""
}

# Find latest backup
find_latest_backup() {
    local latest_file=""

    if [[ "${FROM_S3}" == "true" ]]; then
        if [[ -z "${BACKUP_S3_BUCKET}" ]]; then
            log_error "BACKUP_S3_BUCKET is required for S3 restores"
            exit 2
        fi

        local aws_opts=()
        if [[ -n "${BACKUP_S3_ENDPOINT}" ]]; then
            aws_opts+=(--endpoint-url "${BACKUP_S3_ENDPOINT}")
        fi

        # Find latest in S3
        latest_file="$(aws "${aws_opts[@]}" s3 ls "s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}" --recursive 2>/dev/null | \
            grep '\.sql\.gz$' | sort -k1,2 | tail -1 | awk '{print $NF}')"

        if [[ -z "${latest_file}" ]]; then
            log_error "No backup files found in S3"
            exit 4
        fi

        # Return just the filename for S3 path resolution
        echo "${latest_file}"
    else
        # Find latest local backup
        latest_file="$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null | \
            sort -n | tail -1 | cut -d' ' -f2-)"

        if [[ -z "${latest_file}" ]]; then
            log_error "No backup files found in ${BACKUP_DIR}"
            exit 4
        fi

        echo "${latest_file}"
    fi
}

# Download backup from S3
download_from_s3() {
    local s3_key="$1"
    local temp_file

    temp_file="$(mktemp --suffix=.sql.gz)"
    TEMP_FILES+=("${temp_file}")

    local aws_opts=()
    if [[ -n "${BACKUP_S3_ENDPOINT}" ]]; then
        aws_opts+=(--endpoint-url "${BACKUP_S3_ENDPOINT}")
    fi

    local s3_path
    if [[ "${s3_key}" == s3://* ]]; then
        s3_path="${s3_key}"
    else
        s3_path="s3://${BACKUP_S3_BUCKET}/${s3_key}"
    fi

    log_info "Downloading backup from S3: ${s3_path}"

    if ! aws "${aws_opts[@]}" s3 cp "${s3_path}" "${temp_file}" --quiet; then
        log_error "Failed to download backup from S3"
        exit 4
    fi

    # Also download checksum if available
    local checksum_temp="${temp_file}.sha256"
    if aws "${aws_opts[@]}" s3 cp "${s3_path}.sha256" "${checksum_temp}" --quiet 2>/dev/null; then
        # Fix the path in the checksum file to point to our temp file
        sed -i "s|.*|$(sha256sum "${temp_file}" | awk '{print $1}')  ${temp_file}|" "${checksum_temp}"
        TEMP_FILES+=("${checksum_temp}")
        log_debug "Downloaded checksum file"
    fi

    log_success "Downloaded backup to ${temp_file}"
    echo "${temp_file}"
}

# Resolve backup file path
resolve_backup_file() {
    local input_file="$1"

    if [[ "${FROM_S3}" == "true" ]]; then
        download_from_s3 "${input_file}"
    else
        # Local file resolution
        if [[ -f "${input_file}" ]]; then
            echo "${input_file}"
        elif [[ -f "${BACKUP_DIR}/${input_file}" ]]; then
            echo "${BACKUP_DIR}/${input_file}"
        else
            log_error "Backup file not found: ${input_file}"
            log_error "Checked:"
            log_error "  - ${input_file}"
            log_error "  - ${BACKUP_DIR}/${input_file}"
            log_error ""
            log_error "Use --list to see available backups"
            exit 4
        fi
    fi
}

# Validate backup file
validate_backup_file() {
    local backup_file="$1"

    log_info "Validating backup file: $(basename "${backup_file}")"

    # Check file exists and is readable
    if [[ ! -r "${backup_file}" ]]; then
        log_error "Cannot read backup file: ${backup_file}"
        exit 4
    fi

    # Check file is not empty
    local file_size
    file_size="$(stat -c%s "${backup_file}" 2>/dev/null || stat -f%z "${backup_file}" 2>/dev/null || echo 0)"
    if [[ "${file_size}" -eq 0 ]]; then
        log_error "Backup file is empty: ${backup_file}"
        exit 4
    fi

    log_debug "Backup file size: ${file_size} bytes"

    # Verify checksum if available
    local checksum_file="${backup_file}.sha256"
    if [[ -f "${checksum_file}" ]]; then
        log_info "Verifying checksum..."
        if sha256sum -c "${checksum_file}" --status 2>/dev/null; then
            log_success "Checksum verification passed"
        else
            log_error "Checksum verification FAILED"
            log_error "The backup file may be corrupted"
            log_error ""
            log_error "Expected: $(cat "${checksum_file}")"
            log_error "Actual:   $(sha256sum "${backup_file}")"
            exit 4
        fi
    else
        log_warn "No checksum file found - skipping integrity verification"
        log_warn "Consider adding ${backup_file}.sha256 for data integrity"
    fi

    # Test decompression
    log_debug "Testing backup file decompression..."
    if ! zcat "${backup_file}" 2>/dev/null | head -100 > /dev/null; then
        log_error "Backup file appears to be corrupted (cannot decompress)"
        exit 4
    fi

    # Verify it's a PostgreSQL dump
    local first_lines
    first_lines="$(zcat "${backup_file}" | head -10)"
    if [[ ! "${first_lines}" =~ PostgreSQL ]]; then
        log_error "File does not appear to be a PostgreSQL dump"
        log_error "First 10 lines:"
        echo "${first_lines}" | head -5 >&2
        exit 4
    fi

    # Extract and display backup metadata if available
    local dump_date
    dump_date="$(echo "${first_lines}" | grep -oP 'Dumped.*' | head -1 || echo "unknown")"
    if [[ -n "${dump_date}" && "${dump_date}" != "unknown" ]]; then
        log_info "Backup timestamp: ${dump_date}"
    fi

    log_success "Backup file validation passed"
}

# Get database statistics (for verification)
get_db_stats() {
    local db_name="${1:-${TARGET_DB}}"

    psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${db_name}" \
        -t -A -c "
        SELECT json_build_object(
            'tables', (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'),
            'views', (SELECT count(*) FROM information_schema.views WHERE table_schema = 'public'),
            'indexes', (SELECT count(*) FROM pg_indexes WHERE schemaname = 'public'),
            'total_rows', COALESCE((SELECT sum(n_live_tup) FROM pg_stat_user_tables), 0),
            'db_size', pg_database_size(current_database())
        );
    " 2>/dev/null || echo '{"tables": 0, "views": 0, "indexes": 0, "total_rows": 0, "db_size": 0}'
}

# Create pre-restore backup
create_pre_restore_backup() {
    if [[ "${RESTORE_PRE_BACKUP}" != "true" ]]; then
        log_debug "Pre-restore backup disabled"
        return 0
    fi

    # Check if target database exists
    local db_exists
    db_exists="$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" \
        -t -A -c "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}';" 2>/dev/null || echo "")"

    if [[ -z "${db_exists}" ]]; then
        log_info "Target database ${TARGET_DB} does not exist - skipping pre-restore backup"
        return 0
    fi

    log_info "Creating pre-restore backup..."

    local timestamp
    timestamp="$(date '+%Y%m%d_%H%M%S')"
    local pre_backup_file="${BACKUP_DIR}/${TARGET_DB}_pre_restore_${timestamp}.sql.gz"

    # Create backup directory if needed
    mkdir -p "${BACKUP_DIR}"

    if pg_dump -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" \
        -d "${TARGET_DB}" --no-password --format=plain | gzip > "${pre_backup_file}" 2>/dev/null; then

        local backup_size
        backup_size="$(du -h "${pre_backup_file}" | cut -f1)"
        log_success "Pre-restore backup created: $(basename "${pre_backup_file}") (${backup_size})"

        # Generate checksum
        sha256sum "${pre_backup_file}" > "${pre_backup_file}.sha256"
    else
        log_warn "Could not create pre-restore backup (database may be empty)"
    fi
}

# Confirm restore with user
confirm_restore() {
    local backup_file="$1"

    if [[ "${RESTORE_SKIP_CONFIRM}" == "true" ]]; then
        return 0
    fi

    local backup_size
    backup_size="$(du -h "${backup_file}" | cut -f1)"

    echo ""
    echo -e "${BOLD}========================================${NC}"
    echo -e "${BOLD}     DATABASE RESTORE CONFIRMATION${NC}"
    echo -e "${BOLD}========================================${NC}"
    echo ""
    echo "You are about to restore the database:"
    echo ""
    echo -e "  ${BLUE}Database:${NC}   ${TARGET_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"
    echo -e "  ${BLUE}Backup:${NC}     $(basename "${backup_file}")"
    echo -e "  ${BLUE}Size:${NC}       ${backup_size}"
    echo ""

    if [[ "${DROP_EXISTING}" == "true" ]]; then
        echo -e "  ${RED}${BOLD}WARNING: Existing objects will be DROPPED!${NC}"
        echo ""
    fi

    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        echo -e "  ${BLUE}Mode:${NC}       Schema only (no data)"
    elif [[ "${DATA_ONLY}" == "true" ]]; then
        echo -e "  ${BLUE}Mode:${NC}       Data only (no schema changes)"
    else
        echo -e "  ${BLUE}Mode:${NC}       Full restore (schema + data)"
    fi

    if [[ "${RESTORE_PRE_BACKUP}" == "true" ]]; then
        echo -e "  ${BLUE}Safety:${NC}     Pre-restore backup will be created"
    else
        echo -e "  ${YELLOW}Safety:${NC}     No pre-restore backup (--no-pre-backup)"
    fi

    echo ""
    echo -e "${YELLOW}This operation may take several minutes and cannot be undone!${NC}"
    echo ""

    read -r -p "Type 'yes' to confirm restore: " confirm
    echo ""

    if [[ "${confirm}" != "yes" ]]; then
        log_info "Restore cancelled by user"
        exit 7
    fi
}

# Perform dry run analysis
dry_run_analysis() {
    local backup_file="$1"

    log_info "Performing dry-run analysis..."

    echo ""
    echo "=============================================="
    echo "         Backup File Analysis"
    echo "=============================================="
    echo ""

    # File information
    local file_size
    file_size="$(du -h "${backup_file}" | cut -f1)"
    local line_count
    line_count="$(zcat "${backup_file}" | wc -l)"

    echo "File: $(basename "${backup_file}")"
    echo "Size: ${file_size}"
    echo "Lines: ${line_count}"
    echo ""

    # Count statements by type
    echo "SQL Statement Summary:"
    echo "----------------------"
    zcat "${backup_file}" | grep -E '^(CREATE|ALTER|DROP|INSERT|COPY|SET|COMMENT|GRANT|REVOKE)' | \
        sed 's/ .*//' | sort | uniq -c | sort -rn | head -15 | while read -r count stmt; do
        printf "  %-20s %d\n" "${stmt}" "${count}"
    done
    echo ""

    # List tables
    echo "Tables in backup:"
    echo "-----------------"
    zcat "${backup_file}" | grep -E '^CREATE TABLE' | \
        sed 's/CREATE TABLE \(IF NOT EXISTS \)\?/  /' | \
        sed 's/ *(.*//' | tr -d '"' | sort
    echo ""

    # Estimate data volume from COPY statements
    echo "Data Operations:"
    echo "----------------"
    local copy_count
    copy_count="$(zcat "${backup_file}" | grep -c '^COPY ' || echo 0)"
    local insert_count
    insert_count="$(zcat "${backup_file}" | grep -c '^INSERT ' || echo 0)"
    echo "  COPY statements:   ${copy_count}"
    echo "  INSERT statements: ${insert_count}"
    echo ""

    # Check for RLS policies
    local rls_count
    rls_count="$(zcat "${backup_file}" | grep -c 'CREATE POLICY' || echo 0)"
    if [[ "${rls_count}" -gt 0 ]]; then
        echo "Row-Level Security:"
        echo "-------------------"
        echo "  Policies found: ${rls_count}"
        echo ""
    fi

    # Check for extensions
    local extensions
    extensions="$(zcat "${backup_file}" | grep -E '^CREATE EXTENSION' | sed 's/CREATE EXTENSION \(IF NOT EXISTS \)\?/  /' | sed 's/;.*//')"
    if [[ -n "${extensions}" ]]; then
        echo "Extensions:"
        echo "-----------"
        echo "${extensions}"
        echo ""
    fi

    echo "=============================================="
    echo ""
    log_info "Dry run complete - no changes made"
    log_info "To perform the restore, run without --dry-run"
}

# Ensure target database exists
ensure_database_exists() {
    local db_exists
    db_exists="$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" \
        -t -A -c "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}';" 2>/dev/null || echo "")"

    if [[ -z "${db_exists}" ]]; then
        log_info "Creating database ${TARGET_DB}..."
        psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "postgres" \
            -c "CREATE DATABASE \"${TARGET_DB}\";" 2>&1 || {
            log_error "Failed to create database ${TARGET_DB}"
            exit 5
        }
        log_success "Database ${TARGET_DB} created"
    fi
}

# Perform the restore
perform_restore() {
    local backup_file="$1"
    local restore_start
    restore_start="$(date +%s)"

    log_info "Starting database restore to ${TARGET_DB}..."

    # Get pre-restore stats
    local pre_stats
    pre_stats="$(get_db_stats)"
    log_debug "Pre-restore stats: ${pre_stats}"

    # Ensure target database exists
    ensure_database_exists

    # Drop existing objects if requested
    if [[ "${DROP_EXISTING}" == "true" ]]; then
        log_warn "Dropping existing objects in ${TARGET_DB}..."
        psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" \
            -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;" 2>&1 || {
            log_error "Failed to drop existing objects"
            exit 5
        }
        log_info "Existing objects dropped"
    fi

    # Build psql options
    local psql_opts=(
        -h "${POSTGRES_HOST}"
        -p "${POSTGRES_PORT}"
        -U "${POSTGRES_USER}"
        -d "${TARGET_DB}"
        --no-password
        --echo-errors
        -v ON_ERROR_STOP=1
    )

    if [[ "${VERBOSE}" == "true" ]]; then
        psql_opts+=(--echo-queries)
    fi

    # Execute restore with appropriate filtering
    log_info "Restoring from backup..."

    local restore_result=0
    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        log_info "Mode: Schema only (filtering out data statements)"
        # Filter out COPY blocks and INSERT statements
        zcat "${backup_file}" | \
            awk '/^COPY .* FROM stdin;$/{skip=1; next} /^\\.$/{skip=0; next} !skip && !/^INSERT /' | \
            psql "${psql_opts[@]}" 2>&1 || restore_result=$?

    elif [[ "${DATA_ONLY}" == "true" ]]; then
        log_info "Mode: Data only (filtering schema statements)"
        # Only keep COPY blocks and INSERT statements
        zcat "${backup_file}" | \
            awk '/^COPY .* FROM stdin;$/{print; skip=1; next} /^\\.$/{print; skip=0; next} skip{print} /^INSERT /{print}' | \
            psql "${psql_opts[@]}" 2>&1 || restore_result=$?

    else
        log_info "Mode: Full restore (schema + data)"
        zcat "${backup_file}" | psql "${psql_opts[@]}" 2>&1 || restore_result=$?
    fi

    if [[ ${restore_result} -ne 0 ]]; then
        log_error "Restore failed with exit code ${restore_result}"
        log_error ""
        log_error "Troubleshooting tips:"
        log_error "  1. Check if the target database has conflicting objects (use --drop)"
        log_error "  2. Verify the backup file is not corrupted"
        log_error "  3. Check database user permissions"
        log_error "  4. Review error messages above"
        exit 5
    fi

    local restore_end
    restore_end="$(date +%s)"
    local restore_duration=$((restore_end - restore_start))

    log_success "Restore completed in ${restore_duration} seconds"

    # Get post-restore stats
    local post_stats
    post_stats="$(get_db_stats)"
    log_debug "Post-restore stats: ${post_stats}"

    # Display comparison
    echo ""
    echo "Restore Statistics:"
    echo "-------------------"
    echo "  Duration: ${restore_duration} seconds"

    # Parse stats (basic parsing for display)
    local pre_tables post_tables pre_rows post_rows
    pre_tables=$(echo "${pre_stats}" | grep -oP '"tables":\s*\K\d+' || echo "0")
    post_tables=$(echo "${post_stats}" | grep -oP '"tables":\s*\K\d+' || echo "0")
    pre_rows=$(echo "${pre_stats}" | grep -oP '"total_rows":\s*\K\d+' || echo "0")
    post_rows=$(echo "${post_stats}" | grep -oP '"total_rows":\s*\K\d+' || echo "0")

    echo "  Tables:   ${pre_tables} -> ${post_tables}"
    echo "  Rows:     ${pre_rows} -> ${post_rows}"
    echo ""
}

# Verify restore by running basic checks
verify_restore() {
    log_info "Verifying restore..."

    local verify_result=0

    # Check we can connect
    if ! psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" \
        -c "SELECT 1" > /dev/null 2>&1; then
        log_error "Cannot connect to restored database"
        return 1
    fi

    # Get table count
    local table_count
    table_count="$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" \
        -t -A -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';" 2>/dev/null || echo "0")"

    if [[ "${table_count}" -eq 0 ]] && [[ "${SCHEMA_ONLY}" != "true" ]] && [[ "${DATA_ONLY}" != "true" ]]; then
        log_warn "No tables found after restore - this may indicate a problem"
        verify_result=1
    else
        log_info "Restored ${table_count} tables"
    fi

    # Run ANALYZE for query optimizer
    log_info "Running ANALYZE on restored tables..."
    psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" \
        -c "ANALYZE;" > /dev/null 2>&1 || true

    # Check for RLS policies (important for multi-tenant security)
    local rls_count
    rls_count="$(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${TARGET_DB}" \
        -t -A -c "SELECT count(*) FROM pg_policies;" 2>/dev/null || echo "0")"

    if [[ "${rls_count}" -gt 0 ]]; then
        log_info "Row-Level Security policies: ${rls_count}"
    fi

    if [[ ${verify_result} -eq 0 ]]; then
        log_success "Restore verification passed"
    else
        log_warn "Restore verification completed with warnings"
    fi

    return ${verify_result}
}

# Main execution
main() {
    parse_args "$@"

    log_info "{{ cookiecutter.project_name }} Database Restore v${SCRIPT_VERSION}"

    # Handle list command
    if [[ "${LIST_BACKUPS}" == "true" ]]; then
        validate_config
        list_backups
        exit 0
    fi

    validate_config
    test_connection

    # Determine backup file
    if [[ "${USE_LATEST}" == "true" ]]; then
        BACKUP_FILE="$(find_latest_backup)"
        log_info "Using latest backup: $(basename "${BACKUP_FILE}")"
    elif [[ -z "${BACKUP_FILE}" ]]; then
        log_error "No backup file specified"
        log_error ""
        log_error "Usage:"
        log_error "  ${SCRIPT_NAME} backup_file.sql.gz     # Restore specific file"
        log_error "  ${SCRIPT_NAME} --latest               # Restore most recent"
        log_error "  ${SCRIPT_NAME} --list                 # List available backups"
        log_error ""
        log_error "Use --help for more options"
        exit 2
    fi

    # Resolve full path
    local resolved_file
    resolved_file="$(resolve_backup_file "${BACKUP_FILE}")"

    validate_backup_file "${resolved_file}"

    # Handle dry run
    if [[ "${DRY_RUN}" == "true" ]]; then
        dry_run_analysis "${resolved_file}"
        exit 0
    fi

    # Confirm with user
    confirm_restore "${resolved_file}"

    # Create pre-restore backup
    create_pre_restore_backup

    # Perform restore
    perform_restore "${resolved_file}"

    # Verify restore
    verify_restore || log_warn "Verification had warnings - please review"

    log_success "Database restore completed successfully"
    echo ""
    log_info "Next steps:"
    log_info "  1. Run ./scripts/db-verify.sh for comprehensive validation"
    log_info "  2. Test application connectivity"
    log_info "  3. Verify data integrity"
    echo ""

    exit 0
}

main "$@"
