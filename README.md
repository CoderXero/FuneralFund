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
X-User-Groups: community_leader
```

Supported groups:

* `admin`
* `community_leader`
* `community_user`

When no IDP session or explicit development headers are present, protected routes return `401`.
Header authentication is ignored outside development and testing.

## Environment Variables

Local defaults live in `.env`. Use `.env.example` as the template for new environments and do not commit real secrets.

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

## Current Scope

Implemented:

* Flask app factory
* OIDC login, callback, logout, and session auth
* Public landing page with latest notice
* SQLAlchemy schema
* Alembic/Flask-Migrate baseline
* Member, family, fee, payment, voting, report, and settings APIs
* Member self-service pages for profile/family, payments, voting, settings, and messages
* Leadership Admin area for members, payments, voting, and messages
* Leadership payment settings for Cash App, Venmo, and Zelle with QR codes
* Manual payment proof workflow
* Basic Jinja2 dashboard pages
* Core lifecycle tests

Deferred production integrations are documented in [funeral_fund-spec.md](funeral_fund-spec.md).
