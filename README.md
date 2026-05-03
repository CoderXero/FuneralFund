# FuneralFund

Diaspora Community Funeral Fund Management.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app funeral_fund:create_app init-db
flask --app funeral_fund:create_app run --debug
```

Open `http://127.0.0.1:5000`.

## Development Authentication

The MVP uses request headers as a local stand-in for OIDC claims:

```text
X-User-Email: leader@example.test
X-User-Name: Leader
X-User-Groups: community_leader
```

Supported groups:

* `admin`
* `community_leader`
* `community_user`

When no headers are provided in development, the app creates a local admin user from `DEFAULT_ADMIN_EMAIL`.

## Environment Variables

Local defaults live in `.env`. Use `.env.example` as the template for new environments and do not commit real secrets.

## Tests

```bash
pytest
```

## Current Scope

Implemented:

* Flask app factory
* SQLAlchemy schema
* Member, family, fee, payment, voting, report, and settings APIs
* Manual payment proof workflow
* Basic Jinja2 dashboard pages
* Core lifecycle tests

Deferred production integrations are documented in [funeral_fund-spec.md](funeral_fund-spec.md).
