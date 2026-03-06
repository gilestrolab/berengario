# Billing Module

Paddle payment integration for Berengario's multi-tenant subscription system.

## Architecture

```
src/billing/
├── __init__.py
├── plans.py              # Plan limits, display names, enforcement helpers
├── paddle_service.py     # Paddle API calls, webhook HMAC verification
├── webhook_handler.py    # Webhook event → DB state handlers
└── router.py             # FastAPI billing endpoints
```

## Plan Tiers

| Tier | Queries/month | Storage | Price (GBP/yr) |
|------|--------------|---------|----------------|
| Free | 0 | 0 | - |
| Lite | 500 | 2 GB | £240 |
| Team | 2,000 | 10 GB | £588 |
| Department | 10,000 | 50 GB | £1,788 |

## Trial

New tenants get 3 months free on the Department tier (configurable via `TRIAL_DURATION_DAYS`).

## API Endpoints

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/billing/checkout-config` | GET | Admin | Paddle.js checkout config |
| `/api/billing/portal` | GET | Admin | Subscription management URLs |
| `/api/billing/webhook` | POST | Paddle signature | Webhook receiver |
| `/api/billing/downgrade-to-free` | POST | Admin | Cancel/downgrade |
| `/api/billing/plan-info` | GET | Auth | Current plan, usage, limits |

## Configuration

Set in `.env`:

```
PADDLE_API_KEY=
PADDLE_ENVIRONMENT=sandbox
PADDLE_CLIENT_TOKEN=
PADDLE_WEBHOOK_SECRET=
PADDLE_PRICE_ID_LITE=
PADDLE_PRICE_ID_TEAM=
PADDLE_PRICE_ID_DEPARTMENT=
TRIAL_DURATION_DAYS=90
```
