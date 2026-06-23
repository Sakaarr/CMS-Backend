# CMS Platform — Backend API

FastAPI-based REST API for the Construction Management System.

## Tech Stack

- **Framework:** FastAPI 0.115
- **Language:** Python 3.12
- **Database:** PostgreSQL 16 + asyncpg + SQLAlchemy 2.0
- **Auth:** JWT (access + refresh tokens) with bcrypt
- **Queue:** RabbitMQ (email notifications)
- **Cache:** Redis

## Quick Start

```bash
# Start dependencies
docker compose up -d

# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start dev server
uvicorn src.main:app --reload --port 8000
```

## Environment Variables

Copy `.env` (already provided for development). Required variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string |
| `DATABASE_SYNC_URL` | Sync PostgreSQL connection string |
| `JWT_SECRET_KEY` | Secret for JWT signing (min 32 chars) |
| `FIRST_SUPERADMIN_EMAIL` | Admin email seeded on first run |
| `FIRST_SUPERADMIN_PASSWORD` | Admin password (user forced to change on login) |

## Project Structure

```
src/
├── main.py                    # App entry point
├── core/                      # Config, DB, middleware, exceptions
├── apps/
│   ├── identity/              # Auth, users, permissions
│   ├── tenancy/               # Multi-tenant management
│   ├── projects/              # Projects, sites, milestones
│   ├── boq/                   # Bill of Quantities, rate analysis
│   ├── procurement/           # Vendors, RFQs, POs, GRNs
│   ├── inventory/             # Warehouses, stock, MRs
│   ├── site_ops/              # DPRs, labour, equipment
│   ├── finance/               # Invoices, expenses, payments
│   ├── quality/               # Inspections, NCRs, safety
│   ├── documents/             # Document management
│   ├── approvals/             # Unified approval inbox
│   ├── dashboard/             # Analytics & KPIs
│   └── reports/               # Reporting & exports
└── shared/                    # Shared utilities, response models
```

## API Documentation

Once running, visit `/api/v1/docs` for Swagger UI.
