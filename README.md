# FuneralFund

Diaspora Community Funeral Fund Management.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app funeral_fund:create_app db upgrade
flask --app funeral_fund:create_app run --debug --port 8003
```

Open `http://127.0.0.1:8003`.
The public landing page lives at `/`; signed-in users continue to `/dashboard`.

## Authentication

The app supports OIDC login at `/auth/login` and callback handling at `/auth/callback`.
Configure these values in `.env`:

```text
CLIENT_ID
CLIENT_SECRET
OIDC_OPENID_CONFIG_URL
OIDC_SCOPE
OIDC_CODE_CHALLENGE_METHOD
REDIRECT_URI
LOCAL_REDIRECT_URI
```

`CLIENT_SECRET` must be set for the current confidential-client OAuth flow. If it is blank,
`/auth/login` returns a setup error instead of redirecting to a callback that cannot exchange
the authorization code.

The local default uses PKCE with `OIDC_CODE_CHALLENGE_METHOD=S256`, which causes `/auth/login`
to send a `code_challenge` and `/auth/callback` to exchange the matching `code_verifier`.

In `development` and `testing`, request headers are also supported as an explicit local stand-in for OIDC claims:

```text
X-User-Email: leader@example.test
X-User-Name: Leader
X-User-Groups: Community_leader
```

Supported groups:

* `admin`
* `Community_leader`
* `community_member`

Group matching is case-insensitive. In the app these display as `Admin`, `Leader`, and `Member`.

When no IDP session or explicit development headers are present, protected routes return `401`.
Header authentication is ignored outside development and testing.

## Environment Variables

Local defaults live in `.env`. Use `.env.example` as the template for new environments and do not commit real secrets.

Payment provider API keys and webhook secrets are read from environment variables. For local development, put them in `.env`; for Azure App Service, configure them as App Service application settings. Do not store provider secrets in the web settings screen.

Message archive retention uses `FISCAL_YEAR_END_MONTH` and `FISCAL_YEAR_END_DAY`. Archived messages remain in the database and are retained through the configured fiscal year end.

## Azure Deployment

Current production deployment:

* Resource group: `iyam-b2c-prod-rg`
* App Service plan: `iyam-b2c-prod-plan`
* App Service: `ubuntu-20260510`
* Default hostname: `https://ubuntu-20260510.azurewebsites.net`
* PostgreSQL Flexible Server: `ubuntu-20260510-pg`
* PostgreSQL database: `funeralfund`
* Health check: `GET /readyz`

The app runs on Azure App Service for Linux with Python 3.12. The production database is Azure Database for PostgreSQL Flexible Server. The App Service setting `DATABASE_URL` must use the SQLAlchemy psycopg dialect:

```text
postgresql+psycopg://<user>:<password>@<server>.postgres.database.azure.com:5432/<database>?sslmode=require
```

Production App Service settings must include:

```text
DATABASE_URL
FUNERAL_FUND_ENV=production
SECRET_KEY
OIDC_CLIENT_ID or CLIENT_ID
OIDC_CLIENT_SECRET or CLIENT_SECRET
OIDC_OPENID_CONFIG_URL or OIDC_ISSUER
OIDC_REDIRECT_URI or REDIRECT_URI
OIDC_SCOPE
OIDC_CODE_CHALLENGE_METHOD
SCM_DO_BUILD_DURING_DEPLOYMENT=false
WEBSITE_RUN_FROM_PACKAGE=1
WEBSITES_CONTAINER_START_TIME_LIMIT=1800
```

The startup command used for the current App Service decodes a base64 startup script from `PAMODZI_STARTUP_B64`. The script unpacks the run-from-package zip into `/home/site/funeralfund-app`, creates a persistent virtualenv at `/home/site/funeralfund-venv`, installs `requirements.txt`, runs:

```bash
flask --app funeral_fund:create_app db upgrade
```

and starts Gunicorn:

```bash
gunicorn --bind=0.0.0.0:${PORT:-8000} --workers=2 --timeout=120 'funeral_fund:create_app()'
```

Manual deployment from this repo:

```bash
source .venv/bin/activate
.venv/bin/pytest
git archive --format zip HEAD -o /tmp/funeralfund.zip
az webapp deployment source config-zip \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510 \
  --src /tmp/funeralfund.zip \
  --timeout 900
curl -fsS https://ubuntu-20260510.azurewebsites.net/readyz
```

Custom domain status:

* `ubuntu.zambeziblue.com` is bound to the App Service.
* DNS must point `ubuntu.zambeziblue.com` to `ubuntu-20260510.azurewebsites.net` before a managed TLS certificate can be issued and bound.

Do not delete `iyam-b2c-prod-plan` during redeployments unless all other apps on that shared plan have been moved or removed.

## Message Management

Leaders can manage messages from `/admin/messages`. They can broadcast to all members, community members, or leadership, and they can send direct messages to an individual member by email address. Direct email matching is case-insensitive.

Archived messages are hidden from normal member inboxes but remain available in the leadership message management history until the configured fiscal year end.

## Tests

```bash
.venv/bin/pytest
```

## Migrations

```bash
flask --app funeral_fund:create_app db upgrade
flask --app funeral_fund:create_app db migrate -m "describe change"
```

If an older local SQLite database was created with `init-db` before migrations existed, stamp it once and then upgrade:

```bash
flask --app funeral_fund:create_app db stamp 0001_initial_schema
flask --app funeral_fund:create_app db upgrade
```

## Next Time

Use this checklist when returning to local development:

```bash
source .venv/bin/activate
pip install -r requirements.txt
flask --app funeral_fund:create_app db upgrade
.venv/bin/pytest
flask --app funeral_fund:create_app run --debug --port 8003
```

If a route fails with `sqlite3.OperationalError: no such table`, stop the server, run `flask --app funeral_fund:create_app db upgrade`, then restart it. If the database predates migrations and has no `alembic_version` table, run the one-time stamp command shown above before upgrading.

Sign in through `/auth/login` with IDP credentials. The app no longer creates a hard-coded local admin user.

Next session focus: wire real provider SDKs/API contracts into the integration service boundaries once credentials and provider webhook specifications are available.

## Current Scope

Implemented:

* Flask app factory
* OIDC login, callback, logout, and session auth
* Public landing page with latest notice
* SQLAlchemy schema
* Alembic/Flask-Migrate baseline
* Member, family, fee, payment, voting, report, and settings APIs
* Member self-service pages for profile/family, payments, voting, settings, and messages
* Leadership Admin area for members, payments, voting, and message management
* Leadership broadcast, direct member messaging by email, and message archive workflow
* Leadership payment settings for Cash App, Venmo, and Zelle with QR codes
* Manual payment proof workflow
* Email normalization and protected admin role promotion rules
* Dependant age-out conversion into pending member accounts
* CSV report exports for members, payments, and audit logs
* Admin compliance workspace for user export, anonymization, and audit retention purge
* Payment, WhatsApp, and Blob Storage integration boundaries with explicit setup errors
* Basic Jinja2 dashboard pages
* Core lifecycle, migration, integration-boundary, and compliance tests

Deferred production integrations are documented in [funeral_fund-spec.md](funeral_fund-spec.md).
Version 2 rebuild and operations requirements are documented in [funeral_fund-v2-spec.md](funeral_fund-v2-spec.md).
