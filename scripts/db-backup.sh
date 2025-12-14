#!/usr/bin/env bash
# {{ cookiecutter.project_name }} Database Backup Script
#
# Creates PostgreSQL logical backups using pg_dump with configurable
# retention policy and storage options.
#
# Usage:
#   ./scripts/db-backup.sh                    # Full backup with defaults
#   ./scripts/db-backup.sh --type=daily       # Explicit daily backup
#   ./scripts/db-backup.sh --type=weekly      # Weekly backup (longer retention)
#   ./scripts/db-backup.sh --type=monthly     # Monthly backup (longest retention)
#   ./scripts/db-backup.sh --schema-only      # Schema-only backup
#   ./scripts/db-backup.sh --verify           # Verify backup integrity
#
# Environment Variables:
#   POSTGRES_HOST          - Database host (default: localhost)
#   POSTGRES_PORT          - Database port (default: 5432)
#   POSTGRES_DB            - Database name (default: {{ cookiecutter.postgres_db }})
#   POSTGRES_USER          - Database user (default: {{ cookiecutter.postgres_user }})
#   PGPASSWORD             - Database password (required)
#   BACKUP_DIR             - Local backup directory (default: ./backups)
#   BACKUP_RETENTION_DAILY - Days to keep daily backups (default: 7)
#   BACKUP_RETENTION_WEEKLY - Weeks to keep weekly backups (default: 4)
#   BACKUP_RETENTION_MONTHLY - Months to keep monthly backups (default: 12)
#   BACKUP_S3_BUCKET       - S3 bucket for remote storage (optional)
#   BACKUP_S3_PREFIX       - S3 prefix/folder (default: backups/)
#   BACKUP_S3_ENDPOINT     - S3-compatible endpoint URL (optional, for Minio)
#
# Exit Codes:
#   0 - Success
#   1 - General error
#   2 - Configuration error
#   3 - Database connection error
#   4 - Backup creation error
#   5 - Verification error
#   6 - Upload error
#   7 - Cleanup error

set -euo pipefail

# Script metadata
readonly SCRIPT_NAME="db-backup"
readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-{{ cookiecutter.postgres_db }}}"
POSTGRES_USER="${POSTGRES_USER:-{{ cookiecutter.postgres_user }}}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/backups}"
BACKUP_RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-12}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-backups/}"
BACKUP_S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"

# Runtime options
BACKUP_TYPE="daily"
SCHEMA_ONLY=false
VERIFY_BACKUP=false
VERBOSE=false

# Metrics (for monitoring integration)
BACKUP_START_TIME=""
BACKUP_END_TIME=""
BACKUP_SIZE_BYTES=0

# Logging functions
log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

log_debug() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $*"
    fi
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUCCESS] $*"
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARNING] $*" >&2
}

# Print usage information
usage() {
    cat << EOF
Usage: ${SCRIPT_NAME} [OPTIONS]

Creates PostgreSQL database backups with configurable retention policy.

Options:
    --type=TYPE       Backup type: daily, weekly, monthly (default: daily)
    --schema-only     Create schema-only backup (no data)
    --verify          Verify backup integrity after creation
    --verbose, -v     Enable verbose output
    --help, -h        Show this help message
    --version         Show version information

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, PGPASSWORD
    BACKUP_DIR, BACKUP_RETENTION_DAILY, BACKUP_RETENTION_WEEKLY, BACKUP_RETENTION_MONTHLY
    BACKUP_S3_BUCKET, BACKUP_S3_PREFIX, BACKUP_S3_ENDPOINT

Examples:
    ${SCRIPT_NAME}                              # Daily backup with defaults
    ${SCRIPT_NAME} --type=weekly                # Weekly backup
    ${SCRIPT_NAME} --verify                     # Backup with verification
    ${SCRIPT_NAME} --schema-only --verify       # Schema backup with verification
    BACKUP_DIR=/mnt/backups ${SCRIPT_NAME}      # Custom backup directory

Exit Codes:
    0 - Success
    1 - General error
    2 - Configuration error
    3 - Database connection error
    4 - Backup creation error
    5 - Verification error
    6 - Upload error
    7 - Cleanup error
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
            --type=*)
                BACKUP_TYPE="${1#*=}"
                if [[ ! "${BACKUP_TYPE}" =~ ^(daily|weekly|monthly)$ ]]; then
                    log_error "Invalid backup type: ${BACKUP_TYPE}"
                    log_error "Valid types are: daily, weekly, monthly"
                    exit 2
                fi
                ;;
            --schema-only)
                SCHEMA_ONLY=true
                ;;
            --verify)
                VERIFY_BACKUP=true
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
    log_info "Validating configuration..."

    # Check required password
    if [[ -z "${PGPASSWORD:-}" ]]; then
        log_error "PGPASSWORD environment variable is required"
        log_error "Set it with: export PGPASSWORD=your_password"
        exit 2
    fi

    # Create backup directory if it doesn't exist
    if [[ ! -d "${BACKUP_DIR}" ]]; then
        log_info "Creating backup directory: ${BACKUP_DIR}"
        if ! mkdir -p "${BACKUP_DIR}"; then
            log_error "Failed to create backup directory: ${BACKUP_DIR}"
            exit 2
        fi
    fi

    # Check if backup directory is writable
    if [[ ! -w "${BACKUP_DIR}" ]]; then
        log_error "Backup directory is not writable: ${BACKUP_DIR}"
        exit 2
    fi

    # Check for required tools
    if ! command -v pg_dump &> /dev/null; then
        log_error "pg_dump is required but not installed"
        log_error "Install PostgreSQL client tools: apt-get install postgresql-client"
        exit 2
    fi

    if ! command -v gzip &> /dev/null && ! command -v pigz &> /dev/null; then
        log_error "gzip or pigz is required for compression"
        exit 2
    fi

    if ! command -v sha256sum &> /dev/null; then
        log_error "sha256sum is required for checksum verification"
        exit 2
    fi

    # Check for pg_isready
    if ! command -v pg_isready &> /dev/null; then
        log_warning "pg_isready not found, skipping connection pre-check"
    fi

    # Validate S3 configuration if bucket is specified
    if [[ -n "${BACKUP_S3_BUCKET}" ]]; then
        if ! command -v aws &> /dev/null; then
            log_warning "AWS CLI not found - S3 upload will be skipped"
            log_warning "Install with: pip install awscli or apt-get install awscli"
            BACKUP_S3_BUCKET=""
        fi
    fi

    log_debug "Configuration validated successfully"
    log_debug "  POSTGRES_HOST: ${POSTGRES_HOST}"
    log_debug "  POSTGRES_PORT: ${POSTGRES_PORT}"
    log_debug "  POSTGRES_DB: ${POSTGRES_DB}"
    log_debug "  POSTGRES_USER: ${POSTGRES_USER}"
    log_debug "  BACKUP_DIR: ${BACKUP_DIR}"
    log_debug "  BACKUP_TYPE: ${BACKUP_TYPE}"
    log_debug "  SCHEMA_ONLY: ${SCHEMA_ONLY}"
    log_debug "  VERIFY_BACKUP: ${VERIFY_BACKUP}"
}

# Test database connection
test_connection() {
    log_info "Testing database connection..."

    if command -v pg_isready &> /dev/null; then
        if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -q; then
            log_error "Cannot connect to database at ${POSTGRES_HOST}:${POSTGRES_PORT}"
            log_error "Ensure PostgreSQL is running and accessible"
            exit 3
        fi
    fi

    # Verify we can actually connect and run a query
    if ! psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "SELECT 1" > /dev/null 2>&1; then
        log_error "Database connection test failed"
        log_error "Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
        log_error "Database: ${POSTGRES_DB}"
        log_error "User: ${POSTGRES_USER}"
        exit 3
    fi

    log_debug "Database connection successful"
}

# Generate backup filename
generate_filename() {
    local timestamp
    timestamp="$(date '+%Y%m%d_%H%M%S')"

    local suffix=""
    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        suffix="_schema"
    fi

    echo "${POSTGRES_DB}_${BACKUP_TYPE}_${timestamp}${suffix}.sql.gz"
}

# Create backup
create_backup() {
    local backup_file="$1"
    local backup_path="${BACKUP_DIR}/${backup_file}"

    log_info "Creating ${BACKUP_TYPE} backup: ${backup_file}"
    BACKUP_START_TIME="$(date +%s)"

    # Build pg_dump options
    local pg_dump_opts=(
        -h "${POSTGRES_HOST}"
        -p "${POSTGRES_PORT}"
        -U "${POSTGRES_USER}"
        -d "${POSTGRES_DB}"
        --no-password
        --format=plain
        --no-owner
        --no-privileges
    )

    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        pg_dump_opts+=(--schema-only)
        log_debug "Schema-only backup enabled"
    fi

    if [[ "${VERBOSE}" == "true" ]]; then
        pg_dump_opts+=(--verbose)
    fi

    # Use pigz for parallel compression if available, otherwise gzip
    local compress_cmd="gzip -9"
    if command -v pigz &> /dev/null; then
        compress_cmd="pigz -p 4 -9"
        log_debug "Using pigz for parallel compression"
    else
        log_debug "Using gzip for compression"
    fi

    # Execute backup with compression
    log_debug "Running: pg_dump ${pg_dump_opts[*]} | ${compress_cmd} > ${backup_path}"

    if pg_dump "${pg_dump_opts[@]}" 2>/dev/null | ${compress_cmd} > "${backup_path}"; then
        BACKUP_END_TIME="$(date +%s)"
        BACKUP_SIZE_BYTES="$(stat -c%s "${backup_path}" 2>/dev/null || stat -f%z "${backup_path}" 2>/dev/null || echo 0)"

        local backup_size_human
        backup_size_human="$(du -h "${backup_path}" | cut -f1)"

        local duration=$((BACKUP_END_TIME - BACKUP_START_TIME))

        log_success "Backup created: ${backup_path}"
        log_info "  Size: ${backup_size_human}"
        log_info "  Duration: ${duration} seconds"

        # Generate checksum
        local checksum_file="${backup_path}.sha256"
        if sha256sum "${backup_path}" > "${checksum_file}"; then
            log_debug "Checksum saved: ${checksum_file}"
        else
            log_warning "Failed to generate checksum"
        fi

        # Create a metadata file
        create_metadata "${backup_path}"
    else
        log_error "Failed to create backup"
        rm -f "${backup_path}"
        exit 4
    fi
}

# Create backup metadata file
create_metadata() {
    local backup_path="$1"
    local metadata_file="${backup_path}.meta"

    cat > "${metadata_file}" << EOF
{
    "backup_file": "$(basename "${backup_path}")",
    "database": "${POSTGRES_DB}",
    "host": "${POSTGRES_HOST}",
    "port": "${POSTGRES_PORT}",
    "user": "${POSTGRES_USER}",
    "backup_type": "${BACKUP_TYPE}",
    "schema_only": ${SCHEMA_ONLY},
    "created_at": "$(date -Iseconds)",
    "created_at_unix": ${BACKUP_START_TIME},
    "duration_seconds": $((BACKUP_END_TIME - BACKUP_START_TIME)),
    "size_bytes": ${BACKUP_SIZE_BYTES},
    "pg_dump_version": "$(pg_dump --version | head -1)",
    "script_version": "${SCRIPT_VERSION}",
    "hostname": "$(hostname)"
}
EOF

    log_debug "Metadata saved: ${metadata_file}"
}

# Verify backup integrity
verify_backup() {
    local backup_file="$1"
    local backup_path="${BACKUP_DIR}/${backup_file}"
    local checksum_file="${backup_path}.sha256"

    log_info "Verifying backup integrity..."

    # Verify checksum
    if [[ -f "${checksum_file}" ]]; then
        log_debug "Verifying SHA256 checksum..."
        if sha256sum -c "${checksum_file}" --status 2>/dev/null; then
            log_debug "Checksum verification passed"
        else
            log_error "Checksum verification failed"
            log_error "Backup file may be corrupted"
            exit 5
        fi
    else
        log_warning "No checksum file found, skipping checksum verification"
    fi

    # Test decompression (read first 1000 lines)
    log_debug "Testing backup file decompression..."
    if ! zcat "${backup_path}" 2>/dev/null | head -1000 > /dev/null; then
        log_error "Backup file appears to be corrupted"
        log_error "Cannot decompress: ${backup_path}"
        exit 5
    fi

    # Verify SQL structure
    log_debug "Verifying SQL structure..."
    local first_line
    first_line="$(zcat "${backup_path}" | head -1)"
    if [[ ! "${first_line}" =~ ^--.*PostgreSQL ]]; then
        log_error "Backup does not appear to be valid PostgreSQL dump"
        log_error "First line: ${first_line}"
        exit 5
    fi

    # Check for critical SQL commands
    local has_create=false
    if zcat "${backup_path}" | grep -q "^CREATE"; then
        has_create=true
    fi

    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        if [[ "${has_create}" == "true" ]]; then
            log_debug "Schema backup contains CREATE statements"
        else
            log_warning "Schema backup appears to be empty"
        fi
    fi

    # Count lines in backup
    local line_count
    line_count="$(zcat "${backup_path}" | wc -l)"
    log_debug "Backup contains ${line_count} lines"

    log_success "Backup verification passed"
}

# Upload to S3 (optional)
upload_to_s3() {
    local backup_file="$1"
    local backup_path="${BACKUP_DIR}/${backup_file}"

    if [[ -z "${BACKUP_S3_BUCKET}" ]]; then
        log_debug "S3 upload skipped (BACKUP_S3_BUCKET not configured)"
        return 0
    fi

    log_info "Uploading backup to S3..."

    # Build AWS CLI options
    local aws_opts=()
    if [[ -n "${BACKUP_S3_ENDPOINT}" ]]; then
        aws_opts+=(--endpoint-url "${BACKUP_S3_ENDPOINT}")
        log_debug "Using S3-compatible endpoint: ${BACKUP_S3_ENDPOINT}"
    fi

    local s3_path="s3://${BACKUP_S3_BUCKET}/${BACKUP_S3_PREFIX}${BACKUP_TYPE}/${backup_file}"
    local checksum_file="${backup_path}.sha256"
    local metadata_file="${backup_path}.meta"

    # Upload backup file
    if aws "${aws_opts[@]}" s3 cp "${backup_path}" "${s3_path}" --quiet; then
        log_success "Uploaded backup to ${s3_path}"

        # Also upload checksum
        if [[ -f "${checksum_file}" ]]; then
            aws "${aws_opts[@]}" s3 cp "${checksum_file}" "${s3_path}.sha256" --quiet
            log_debug "Uploaded checksum to S3"
        fi

        # Also upload metadata
        if [[ -f "${metadata_file}" ]]; then
            aws "${aws_opts[@]}" s3 cp "${metadata_file}" "${s3_path}.meta" --quiet
            log_debug "Uploaded metadata to S3"
        fi
    else
        log_error "Failed to upload backup to S3"
        log_error "Bucket: ${BACKUP_S3_BUCKET}"
        log_error "Path: ${s3_path}"
        exit 6
    fi
}

# Cleanup old backups based on retention policy
cleanup_old_backups() {
    log_info "Cleaning up old backups..."

    local retention_days
    case "${BACKUP_TYPE}" in
        daily)
            retention_days="${BACKUP_RETENTION_DAILY}"
            ;;
        weekly)
            retention_days=$((BACKUP_RETENTION_WEEKLY * 7))
            ;;
        monthly)
            retention_days=$((BACKUP_RETENTION_MONTHLY * 30))
            ;;
    esac

    log_debug "Retention period for ${BACKUP_TYPE} backups: ${retention_days} days"

    local pattern="${POSTGRES_DB}_${BACKUP_TYPE}_*.sql.gz"
    local count=0

    # Find and remove old backups
    while IFS= read -r -d '' file; do
        if [[ -f "${file}" ]]; then
            log_debug "Removing old backup: ${file}"
            rm -f "${file}" "${file}.sha256" "${file}.meta"
            ((count++))
        fi
    done < <(find "${BACKUP_DIR}" -name "${pattern}" -type f -mtime "+${retention_days}" -print0 2>/dev/null || true)

    if [[ ${count} -gt 0 ]]; then
        log_info "Removed ${count} old backup(s) older than ${retention_days} days"
    else
        log_debug "No old backups to remove"
    fi

    # Report current backup status
    local current_count
    current_count="$(find "${BACKUP_DIR}" -name "${pattern}" -type f 2>/dev/null | wc -l || echo 0)"
    log_debug "Current ${BACKUP_TYPE} backup count: ${current_count}"
}

# Write metrics for monitoring (Prometheus textfile collector format)
write_metrics() {
    local backup_file="$1"
    local backup_path="${BACKUP_DIR}/${backup_file}"
    local metrics_dir="${BACKUP_DIR}/metrics"

    # Only write metrics if directory exists or can be created
    if [[ ! -d "${metrics_dir}" ]]; then
        if ! mkdir -p "${metrics_dir}" 2>/dev/null; then
            log_debug "Cannot create metrics directory, skipping metrics"
            return 0
        fi
    fi

    local metrics_file="${metrics_dir}/backup_${POSTGRES_DB}.prom"

    cat > "${metrics_file}" << EOF
# HELP backup_last_success_timestamp Unix timestamp of last successful backup
# TYPE backup_last_success_timestamp gauge
backup_last_success_timestamp{database="${POSTGRES_DB}",type="${BACKUP_TYPE}"} ${BACKUP_END_TIME}

# HELP backup_size_bytes Size of last backup in bytes
# TYPE backup_size_bytes gauge
backup_size_bytes{database="${POSTGRES_DB}",type="${BACKUP_TYPE}"} ${BACKUP_SIZE_BYTES}

# HELP backup_duration_seconds Duration of backup operation in seconds
# TYPE backup_duration_seconds gauge
backup_duration_seconds{database="${POSTGRES_DB}",type="${BACKUP_TYPE}"} $((BACKUP_END_TIME - BACKUP_START_TIME))
EOF

    log_debug "Metrics written to ${metrics_file}"
}

# List existing backups
list_backups() {
    log_info "Existing backups in ${BACKUP_DIR}:"

    local total_size=0
    local count=0

    while IFS= read -r file; do
        if [[ -n "${file}" ]]; then
            local size
            size="$(du -h "${file}" | cut -f1)"
            local date
            date="$(stat -c %y "${file}" 2>/dev/null | cut -d. -f1 || stat -f "%Sm" "${file}" 2>/dev/null || echo "unknown")"
            echo "  $(basename "${file}") - ${size} - ${date}"
            ((count++))
        fi
    done < <(find "${BACKUP_DIR}" -name "*.sql.gz" -type f 2>/dev/null | sort -r | head -20)

    if [[ ${count} -eq 0 ]]; then
        echo "  No backups found"
    else
        echo ""
        echo "  Total: ${count} backup(s)"
    fi
}

# Main execution
main() {
    parse_args "$@"

    log_info "Starting {{ cookiecutter.project_name }} database backup"
    log_info "Database: ${POSTGRES_DB}@${POSTGRES_HOST}:${POSTGRES_PORT}"
    log_info "Backup type: ${BACKUP_TYPE}"
    if [[ "${SCHEMA_ONLY}" == "true" ]]; then
        log_info "Mode: Schema-only (no data)"
    fi

    validate_config
    test_connection

    local backup_file
    backup_file="$(generate_filename)"

    create_backup "${backup_file}"

    if [[ "${VERIFY_BACKUP}" == "true" ]]; then
        verify_backup "${backup_file}"
    fi

    upload_to_s3 "${backup_file}"
    cleanup_old_backups
    write_metrics "${backup_file}"

    log_success "Backup completed successfully: ${backup_file}"

    if [[ "${VERBOSE}" == "true" ]]; then
        echo ""
        list_backups
    fi

    exit 0
}

main "$@"
