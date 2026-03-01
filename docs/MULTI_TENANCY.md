# Multi-Tenancy Deployment Guide

Berengario supports multi-tenant mode, where a single deployment serves multiple organizations with fully isolated data. Each tenant gets its own database, document storage, ChromaDB collection, and email routing.

## Architecture

### Data Isolation

| Layer | Single-Tenant | Multi-Tenant |
|-------|--------------|--------------|
| **Database** | One shared DB | Per-tenant DB (auto-created) |
| **Documents** | `data/kb/` | `data/tenants/{slug}/documents/` (local) or S3 bucket |
| **ChromaDB** | `data/chroma_db/` | `data/tenants/{slug}/chroma_db/` |
| **Config** | `data/config/` | Per-tenant config in tenant DB |
| **Email** | Single inbox | TenantEmailRouter maps addresses to tenants |

### Platform Database

A shared **platform database** (`berengario_platform`) stores cross-tenant data:

- **Tenant** — slug, display name, domain, status, settings JSON
- **TenantUser** — user-tenant membership with roles (owner, admin, member)
- **TenantEncryptionKey** — encrypted per-tenant keys (envelope encryption)
- **JoinRequest** — pending tenant join requests

Each tenant also gets its own isolated database (`berengario_tenant_{slug}`) for conversations, messages, and processing stats.

### Key Components

- **TenantContext** — Frozen dataclass bundling tenant config; created via `from_settings()` (ST) or `from_tenant()` (MT)
- **TenantComponentFactory** — LRU-cached factory that builds per-tenant KB, RAG, QueryHandler, ConversationManager stacks
- **ComponentResolver** — Bridge between ST and MT modes; routes use it without knowing which mode is active
- **TenantEmailRouter** — Maps incoming email addresses to tenant slugs for email processing
- **TenantProvisioner** — Orchestrates tenant creation (DB, storage, encryption) with rollback on failure

## Prerequisites

- **MariaDB** — Required for MT mode (both platform and tenant databases)
- **Docker** — Recommended deployment method
- **Python 3.11+** — If running without Docker

## Quick Setup

### 1. Enable Multi-Tenant Mode

Add to your `.env` file:

```env
MULTI_TENANT=true
PLATFORM_DB_HOST=mariadb
PLATFORM_DB_PORT=3306
PLATFORM_DB_NAME=berengario_platform
PLATFORM_DB_USER=berengario
PLATFORM_DB_PASSWORD=your_secure_password
```

### 2. Start Services

```bash
docker-compose up -d
```

The platform database and tables are auto-created on first startup.

### 3. Access Onboarding

Navigate to `http://localhost:8000/onboarding` to create the first tenant. The first user to onboard becomes the tenant owner.

## Storage Backends

### Local Storage (Default)

Zero configuration required. Tenant files are stored under `data/tenants/{slug}/`:

```
data/tenants/
  acme-corp/
    documents/
    chroma_db/
  other-org/
    documents/
    chroma_db/
```

Set in `.env`:
```env
STORAGE_BACKEND=local
```

### S3 / MinIO Storage

For production deployments or when you need object storage:

```env
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=http://minio:9000   # or https://s3.amazonaws.com
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_REGION=us-east-1
S3_BUCKET_PREFIX=berengario-tenant-
```

Each tenant gets its own bucket: `berengario-tenant-{slug}`.

To start MinIO alongside Berengario:

```bash
docker-compose --profile multitenant up -d
```

This starts the MinIO container (S3-compatible) on ports 9000 (API) and 9001 (web console).

## Encryption

Optional envelope encryption protects tenant data at rest. When enabled, each new tenant gets a unique **Tenant Encryption Key (TEK)** encrypted by the **Master Encryption Key (MEK)**.

### Setup

Generate a master key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add to `.env`:

```env
MASTER_ENCRYPTION_KEY=your_generated_key_here
```

### What It Protects

- Per-tenant encryption keys stored in the platform database
- Can be extended to encrypt tenant documents at rest

### Key Rotation

The MEK can be rotated by re-encrypting all TEKs. This is a platform admin operation.

## Docker Deployment

### Standard MT Deployment

```bash
# Configure .env with MT settings (see Quick Setup above)
docker-compose up -d
```

The existing MariaDB container hosts both the platform DB and all tenant DBs. No additional database container is needed.

### With S3 Storage (MinIO)

```bash
docker-compose --profile multitenant up -d
```

This adds a MinIO container for S3-compatible object storage.

### Volume Mounts

The `data/tenants/` directory is automatically mounted in all service containers for local storage persistence.

## Tenant Provisioning

### Via Onboarding UI

1. Navigate to `/onboarding`
2. Enter organization name and admin email
3. System creates tenant (DB, storage, default config)
4. Admin receives confirmation and can invite team members

### Invite Codes

Tenant owners/admins can generate invite codes from the team management panel. New users redeem codes to join a tenant.

### Join Requests

Users can request to join a tenant. Tenant admins approve or deny from the admin panel.

## Database Schema Management

Tenant databases are created automatically by `TenantProvisioner` using SQLAlchemy's `create_all()`. This handles:

- Initial table creation for new tenants
- The platform database schema is also auto-created on startup

For schema migrations on existing tenants, SQL migration scripts can be placed in `migrations/` and applied via the CLI or manually.

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MULTI_TENANT` | `false` | Enable multi-tenant mode |
| `PLATFORM_DOMAIN` | `berengar.io` | Platform domain for tenant email addresses |
| `PLATFORM_BASE_URL` | `https://berengar.io` | Base URL for the platform |
| `PLATFORM_DB_HOST` | `localhost` | Platform database host |
| `PLATFORM_DB_PORT` | `3306` | Platform database port |
| `PLATFORM_DB_NAME` | `berengario_platform` | Platform database name |
| `PLATFORM_DB_USER` | `berengario` | Platform database username |
| `PLATFORM_DB_PASSWORD` | *(empty)* | Platform database password |
| `STORAGE_BACKEND` | `local` | Storage backend: `local` or `s3` |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | S3-compatible endpoint URL |
| `S3_ACCESS_KEY` | *(empty)* | S3 access key |
| `S3_SECRET_KEY` | *(empty)* | S3 secret key |
| `S3_REGION` | `us-east-1` | S3 region |
| `S3_BUCKET_PREFIX` | `berengario-tenant-` | Prefix for per-tenant S3 buckets |
| `MASTER_ENCRYPTION_KEY` | *(empty)* | Master key for tenant encryption (optional) |
| `TENANT_DB_POOL_SIZE` | `3` | Connection pool size per tenant DB |
| `TENANT_DB_MAX_CACHED` | `50` | Max tenant DB connections in LRU cache |

## Differences from Single-Tenant Mode

| Feature | Single-Tenant | Multi-Tenant |
|---------|--------------|--------------|
| FileWatcher | Active (monitors `data/documents/`) | Disabled (documents ingested via email/upload) |
| Email routing | Single inbox | Per-tenant routing via `TenantEmailRouter` |
| Authentication | Whitelist-based OTP | Whitelist + tenant membership |
| Admin panel | Global | Per-tenant with team management |
| KB storage | Shared ChromaDB | Per-tenant ChromaDB instances |
