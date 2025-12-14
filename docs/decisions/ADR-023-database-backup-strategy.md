# ADR-023: Database Backup Strategy

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2025-12-06 |
| **Decision Makers** | Project Team |

## Context

{{ cookiecutter.project_name }} requires a reliable database backup strategy to protect against data loss, enable disaster recovery, and support operational procedures such as database migrations and environment cloning.

### Requirements

The backup strategy must support:

1. **Recovery Point Objective (RPO)**: Maximum acceptable data loss
   - Development: 24 hours (daily backups sufficient)
   - Production: Should support near-zero with PITR option

2. **Recovery Time Objective (RTO)**: Maximum acceptable downtime
   - Target: < 1 hour for full database restore
   - < 10 minutes for selective data recovery

3. **Operational Needs**:
   - Regular automated backups
   - Multiple retention tiers (daily, weekly, monthly)
   - Remote storage for disaster recovery
   - Ability to restore to specific point in time (future enhancement)

### Constraints

- PostgreSQL as the database (version {{ cookiecutter.postgres_version }})
- Template must work across various deployment environments (Docker, Kubernetes, VMs)
- Minimal external dependencies for core backup functionality
- Optional cloud storage integration (S3-compatible)

## Decision

We implement a **logical backup strategy using pg_dump** with the following characteristics:

### 1. Backup Method: pg_dump (Logical Backups)

**Choice**: Use `pg_dump` for all regular backups

**Rationale**:
- Cross-version compatibility (can restore to different PostgreSQL versions)
- Selective restore capability (individual tables/rows)
- Human-readable SQL output for debugging and auditing
- Smaller backup size for typical application databases
- No need for PostgreSQL superuser privileges
- Works identically across all deployment environments

### 2. Backup Format: Plain-Text SQL with Compression

**Choice**: Generate plain-text SQL dumps compressed with gzip

**Format**: `{database}_{type}_{timestamp}.sql.gz`

**Rationale**:
- Can be inspected and modified if needed
- Works with standard Unix tools (zcat, grep, etc.)
- No special restore tools required beyond psql
- Good compression ratio (~10:1 typical)
- Can be piped directly for streaming operations

### 3. Retention Policy: Tiered Retention

**Choice**: Implement three retention tiers

| Tier | Retention | Purpose |
|------|-----------|---------|
| Daily | 7 days | Recent recovery, development |
| Weekly | 4 weeks | Point-in-time recovery window |
| Monthly | 12 months | Compliance, long-term archive |

**Rationale**:
- Balances storage costs with recovery options
- Provides multiple recovery points at different granularities
- Meets common compliance requirements (1-year retention)
- Configurable via environment variables for different needs

### 4. Storage: Local with Optional S3

**Choice**: Primary storage local, optional sync to S3-compatible storage

**Rationale**:
- Local storage ensures fast backup/restore operations
- S3 integration provides off-site disaster recovery
- S3 lifecycle policies can manage long-term retention
- Works with any S3-compatible storage (AWS, MinIO, etc.)
- Optional dependency - core functionality works without cloud access

### 5. Verification: Checksum and Structure Validation

**Choice**: Generate SHA256 checksums and validate SQL structure on restore

**Rationale**:
- Detects corruption before attempting restore
- Quick validation without full restore
- Standard checksum format compatible with verification tools
- Structure validation catches truncated or incomplete dumps

### 6. Scheduling: External Scheduler

**Choice**: Provide scripts, rely on external scheduling (cron, Kubernetes CronJob)

**Rationale**:
- Flexibility to use platform-native scheduling
- No additional daemon required
- Works with existing monitoring and alerting
- Clear separation of concerns

## Consequences

### Positive

1. **Simple to understand**: Shell scripts with clear logic
2. **Portable**: Works across Docker, Kubernetes, VMs, bare metal
3. **Low dependencies**: Only requires PostgreSQL client tools
4. **Debuggable**: Plain SQL backups can be inspected
5. **Flexible**: Environment variables for all configuration
6. **Testable**: Easy to validate in CI/CD pipelines

### Negative

1. **No built-in PITR**: Requires additional configuration for point-in-time recovery
2. **Full backups only**: No incremental backup support
3. **Scaling limits**: pg_dump may be slow for very large databases (>100GB)
4. **Manual scheduling**: Requires external cron/scheduler setup

### Neutral

1. **Compression trade-off**: gzip is universally available but not the fastest; pigz used when available for parallel compression
2. **Metadata files**: Additional .meta and .sha256 files created alongside backups for verification and tracking

## Alternatives Considered

### Alternative 1: pg_basebackup (Physical Backups)

**Approach**: Use PostgreSQL physical backups that copy the entire data directory.

**Strengths**:
- Fastest backup and restore for large databases
- Required for true point-in-time recovery (PITR)
- Captures entire cluster state

**Why Not Chosen**:
- Requires same PostgreSQL major version for restore
- Larger backup size (entire data directory)
- More complex setup (WAL archiving configuration)
- Requires superuser or replication privileges
- Less flexible for selective recovery

Physical backups are documented as a future enhancement for teams that need PITR or have databases >100GB.

### Alternative 2: pg_dump Custom Format

**Approach**: Use pg_dump's custom format (`-Fc`) instead of plain SQL.

**Strengths**:
- Supports parallel restore
- Selective restore built-in
- Slightly smaller than SQL

**Why Not Chosen**:
- Requires pg_restore tool (not just psql)
- Not human-readable for debugging
- Version-specific format may cause compatibility issues
- Plain SQL provides better portability for template use case

### Alternative 3: Third-Party Backup Tools (Barman, pgBackRest)

**Approach**: Use enterprise-grade PostgreSQL backup solutions.

**Strengths**:
- Full-featured backup management
- Built-in PITR support
- Incremental backups
- Better for enterprise scale

**Why Not Chosen**:
- Additional infrastructure required (Barman server)
- More complex setup and configuration
- Larger dependency footprint
- Overkill for starter template scope

These tools are recommended for production deployments with complex requirements but add too much complexity for a starter template.

### Alternative 4: Database-as-a-Service Managed Backups

**Approach**: Use cloud provider managed backup features (RDS, Cloud SQL, etc.).

**Strengths**:
- Zero configuration
- Automatic PITR
- Managed by provider

**Why Not Chosen**:
- Not portable across providers
- Not available for self-hosted deployments
- Cost implications
- Template focuses on self-hosted deployments

Teams using managed databases should use provider backup features instead of these scripts.

## Implementation

### File Structure

```
scripts/
  db-backup.sh        # Main backup script
  db-restore.sh       # Main restore script

backups/              # Default backup location
  .gitkeep
```

### Interface

```bash
# Backup
./scripts/db-backup.sh                    # Daily backup
./scripts/db-backup.sh --type=weekly      # Weekly backup
./scripts/db-backup.sh --verify           # With verification
./scripts/db-backup.sh --schema-only      # Schema only

# Restore
./scripts/db-restore.sh backup_file.sql.gz   # Restore from file
./scripts/db-restore.sh --latest             # Restore most recent
./scripts/db-restore.sh --dry-run backup.sql # Verify without restore
./scripts/db-restore.sh --list               # List available backups
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | localhost | Database host |
| `POSTGRES_PORT` | 5432 | Database port |
| `POSTGRES_DB` | {{ cookiecutter.postgres_db }} | Database name |
| `POSTGRES_USER` | {{ cookiecutter.postgres_user }} | Database user |
| `PGPASSWORD` | (required) | Database password |
| `BACKUP_DIR` | ./backups | Backup storage directory |
| `BACKUP_RETENTION_DAILY` | 7 | Days to keep daily backups |
| `BACKUP_RETENTION_WEEKLY` | 4 | Weeks to keep weekly backups |
| `BACKUP_RETENTION_MONTHLY` | 12 | Months to keep monthly backups |
| `BACKUP_S3_BUCKET` | (none) | S3 bucket for remote storage |
| `BACKUP_S3_PREFIX` | backups/ | S3 prefix for backups |
| `BACKUP_S3_ENDPOINT` | (none) | S3-compatible endpoint URL |

### Backup Metadata

Each backup generates three files:
- `{name}.sql.gz` - Compressed SQL dump
- `{name}.sql.gz.sha256` - SHA256 checksum
- `{name}.sql.gz.meta` - JSON metadata (timestamp, size, duration, etc.)

### Prometheus Metrics

The backup script writes Prometheus-compatible metrics to `backups/metrics/`:

```prometheus
backup_last_success_timestamp{database="mydb",type="daily"} 1701878400
backup_size_bytes{database="mydb",type="daily"} 1048576
backup_duration_seconds{database="mydb",type="daily"} 12
```

## Future Enhancements

The following are documented as potential future improvements:

1. **Point-in-Time Recovery (PITR)**
   - Configure WAL archiving
   - Add pg_basebackup for base snapshots
   - Document recovery_target_time usage

2. **Incremental Backups**
   - Investigate pgBackRest for incremental support
   - Reduce storage requirements for large databases

3. **Backup Encryption**
   - Add GPG encryption for backups at rest
   - Key management documentation

4. **Parallel Backup/Restore**
   - Use pg_dump --jobs for parallel dump
   - Use custom format with pg_restore --jobs

5. **Monitoring Integration**
   - Prometheus alerts for backup failures
   - Grafana dashboard for backup health

## Related ADRs

- [ADR-017: Optional Observability Stack](./ADR-017-optional-observability-stack.md) - Follows optional feature pattern for S3 integration
- [ADR-019: GitHub Actions CI/CD](./ADR-019-github-actions-cicd.md) - CI integration for backup script testing

## Implementation References

- `scripts/db-backup.sh` - Main backup script
- `scripts/db-restore.sh` - Restore and recovery script
- `backups/` - Default backup directory
- `docs/operations/database-recovery.md` - Recovery procedures (if exists)

## External References

- [PostgreSQL Backup Documentation](https://www.postgresql.org/docs/current/backup.html)
- [pg_dump Manual](https://www.postgresql.org/docs/current/app-pgdump.html)
- [pg_restore Manual](https://www.postgresql.org/docs/current/app-pgrestore.html)
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html)
