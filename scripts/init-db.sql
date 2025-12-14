-- Knowledge Mapper Database Initialization
-- This script runs automatically when the database is first created

-- ========================================
-- STEP 1: Enable Required Extensions
-- ========================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ========================================
-- STEP 2: Create Database Roles
-- ========================================
-- Migration User: For running Alembic migrations
-- Has BYPASSRLS privilege to manage schema without RLS restrictions
CREATE ROLE knowledge_mapper_migration_user WITH
    LOGIN
    PASSWORD 'migration_password_dev'
    CREATEDB
    BYPASSRLS
    NOINHERIT
    NOSUPERUSER;

COMMENT ON ROLE knowledge_mapper_migration_user IS
    'Administrative user for running Alembic migrations. Has BYPASSRLS privilege for schema management.';

-- Application User: For application runtime queries
-- NO BYPASSRLS - RLS policies will be enforced
CREATE ROLE knowledge_mapper_app_user WITH
    LOGIN
    PASSWORD 'app_password_dev'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;

COMMENT ON ROLE knowledge_mapper_app_user IS
    'Application runtime user. NO BYPASSRLS - RLS policies are enforced for tenant isolation.';

-- ========================================
-- STEP 3: Create Schema Version Table
-- ========================================
CREATE TABLE IF NOT EXISTS schema_version (
    version VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Insert initial schema version
INSERT INTO schema_version (version, description)
VALUES ('1.0.0', 'Initial database setup with separate migration and application roles')
ON CONFLICT (version) DO NOTHING;

-- ========================================
-- STEP 4: Create Keycloak Database
-- ========================================
-- Create separate database for Keycloak OAuth provider
CREATE DATABASE keycloak_db
    WITH
    OWNER = knowledge_mapper_migration_user
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.utf8'
    LC_CTYPE = 'en_US.utf8'
    TEMPLATE = template0;

-- ========================================
-- STEP 5: Grant Database Privileges
-- ========================================
-- Grant all privileges to migration user for schema management
GRANT ALL PRIVILEGES ON DATABASE knowledge_mapper_db TO knowledge_mapper_migration_user;
GRANT ALL PRIVILEGES ON DATABASE keycloak_db TO knowledge_mapper_migration_user;

-- Grant connect privilege to application user
GRANT CONNECT ON DATABASE knowledge_mapper_db TO knowledge_mapper_app_user;

-- Grant usage on public schema to application user
GRANT USAGE ON SCHEMA public TO knowledge_mapper_app_user;

-- Grant CREATE privilege on public schema to migration user (required for Alembic migrations)
GRANT CREATE ON SCHEMA public TO knowledge_mapper_migration_user;

-- ========================================
-- STEP 6: Set Default Privileges
-- ========================================
-- Ensure future tables created by migration user are accessible to app user
ALTER DEFAULT PRIVILEGES FOR ROLE knowledge_mapper_migration_user IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO knowledge_mapper_app_user;

-- Ensure future sequences are accessible to app user
ALTER DEFAULT PRIVILEGES FOR ROLE knowledge_mapper_migration_user IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO knowledge_mapper_app_user;

-- ========================================
-- STEP 7: Grant Keycloak Access
-- ========================================
-- Grant keycloak_db privileges to main user (for Keycloak)
GRANT ALL PRIVILEGES ON DATABASE keycloak_db TO knowledge_mapper_user;

-- ========================================
-- STEP 8: Verification
-- ========================================
-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Knowledge Mapper Database Initialized';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Database Roles Created:';
    RAISE NOTICE '  - knowledge_mapper_migration_user (BYPASSRLS=true, for migrations)';
    RAISE NOTICE '  - knowledge_mapper_app_user (BYPASSRLS=false, for application runtime)';
    RAISE NOTICE '';
    RAISE NOTICE 'Databases Created:';
    RAISE NOTICE '  - knowledge_mapper_db (main application database)';
    RAISE NOTICE '  - keycloak_db (OAuth provider database)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next Steps:';
    RAISE NOTICE '  1. Run "alembic upgrade head" to apply schema migrations';
    RAISE NOTICE '  2. Migrations will use knowledge_mapper_migration_user';
    RAISE NOTICE '  3. Application runtime will use knowledge_mapper_app_user';
    RAISE NOTICE '============================================';
END $$;
