-- init-databases.sql
--
-- PostgreSQL initialisation script run by the official postgres Docker image
-- on first container start (when the data directory is empty).
--
-- The primary database (agentcompany_core) is created automatically by the
-- POSTGRES_DB environment variable.  This script creates the additional
-- databases required by the other platform services.
--
-- All databases are owned by the single application superuser defined via
-- POSTGRES_USER.  In a hardened production deployment you would create
-- separate roles with least-privilege grants instead.

\set ON_ERROR_STOP on

-- Outline wiki
SELECT 'CREATE DATABASE outline'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'outline')
\gexec

-- Mattermost team chat
SELECT 'CREATE DATABASE mattermost'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mattermost')
\gexec

-- Keycloak identity provider
SELECT 'CREATE DATABASE keycloak'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')
\gexec

-- Grant all privileges on each database to the application user.
-- The \gexec trick above runs the SELECT result as SQL, so direct GRANT
-- statements are safe here because the databases now exist.
GRANT ALL PRIVILEGES ON DATABASE outline     TO :POSTGRES_USER;
GRANT ALL PRIVILEGES ON DATABASE mattermost  TO :POSTGRES_USER;
GRANT ALL PRIVILEGES ON DATABASE keycloak    TO :POSTGRES_USER;

-- agentcompany_core already exists (POSTGRES_DB) — grant explicitly for clarity
GRANT ALL PRIVILEGES ON DATABASE agentcompany_core TO :POSTGRES_USER;

-- Useful: enable pg_trgm for fuzzy text search in agentcompany_core
\connect agentcompany_core
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect outline
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\connect mattermost
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\connect keycloak
-- Keycloak manages its own schema; no extensions needed.
