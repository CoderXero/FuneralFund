# FuneralFund Version 2 System Specification

## Version

2.0.0

## Purpose

This specification defines the target system for rebuilding FuneralFund v2 from a clean repository. It covers the application architecture, OAuth provider integration, GitHub and `gh` workflow, CI/CD pipeline, and Azure App Service deployment model.

## Product Scope

FuneralFund v2 is a secure community funeral fund management system for diaspora associations. It supports:

* OIDC login and role mapping
* Leadership member approval
* Member and family lifecycle management
* Recurring fees, one-time notices, payment proof, and payment verification
* Voting and governance workflows
* Broadcast and direct messaging
* Audit logging and compliance exports
* Azure-hosted production deployment with PostgreSQL

## Reference Implementation

The v1 implementation uses:

* Python 3.12+
* Flask application factory: `funeral_fund:create_app`
* Jinja2 server-rendered pages
* Flask-SQLAlchemy
* Flask-Migrate and Alembic
* Authlib OIDC client
* Gunicorn
* Pytest

V2 may keep this stack unless a migration is explicitly approved. Rebuilds must preserve current route contracts unless a breaking API version is introduced.

## Repository Requirements

Expected repository structure:

```text
funeral_fund/
  __init__.py
  api.py
  auth.py
  config.py
  csrf.py
  extensions.py
  integrations.py
  models.py
  services.py
  web.py
migrations/
templates/
tests/
.github/workflows/
.env.example
README.md
requirements.txt
pyproject.toml
```

Required root commands:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app funeral_fund:create_app db upgrade
.venv/bin/pytest
```

## Runtime Configuration

All secrets and environment-specific values must come from environment variables or Azure App Service settings. No production secret may be committed to git.

Required settings:

```text
FLASK_APP=funeral_fund:create_app
FUNERAL_FUND_ENV=production
DATABASE_URL=postgresql+psycopg://...
SECRET_KEY=<strong random value>
OIDC_CLIENT_ID=<client id>
OIDC_CLIENT_SECRET=<client secret>
OIDC_REDIRECT_URI=https://<host>/auth/callback
OIDC_OPENID_CONFIG_URL=https://iam.zambeziblue.com/.well-known/openid-configuration
OIDC_SCOPE=openid email profile groups
OIDC_CODE_CHALLENGE_METHOD=S256
SESSION_TIMEOUT_MINUTES=60
AUDIT_RETENTION_DAYS=2555
FISCAL_YEAR_END_MONTH=12
FISCAL_YEAR_END_DAY=31
```

The application must also accept the current aliases:

```text
CLIENT_ID
CLIENT_SECRET
REDIRECT_URI
OIDC_ISSUER
```

## OAuth Provider

Provider: ZambeziBlue IAM

Issuer:

```text
https://iam.zambeziblue.com
```

Discovery document:

```text
https://iam.zambeziblue.com/.well-known/openid-configuration
```

JWKS endpoint:

```text
https://iam.zambeziblue.com/.well-known/jwks.json
```

OAuth flow:

1. User opens `/auth/login`.
2. App redirects to the provider authorization endpoint.
3. App sends `scope=openid email profile groups`.
4. App uses PKCE with `S256`.
5. Provider redirects to `/auth/callback`.
6. App exchanges authorization code for tokens.
7. App reads `email`, `name` or `preferred_username`, `sub`, and `groups` or `roles`.
8. App upserts the local user record.
9. App assigns local role from IDP group membership.

Production callback:

```text
https://ubuntu.zambeziblue.com/auth/callback
```

Local callback:

```text
http://localhost:8003/auth/callback
```

Role mapping:

```text
admin -> admin
community_leader -> community_admin
community_admin -> community_admin
community_member -> community_user
community_user -> community_user
```

Header-based authentication is allowed only in `development` and `testing`.

## Data Model

V2 must include these core entities:

* `users`
* `family_members`
* `fees`
* `notices`
* `payments`
* `votes`
* `vote_options`
* `vote_casts`
* `settings`
* `messages`
* `audit_logs`

Migrations must be Alembic-based and must run cleanly on PostgreSQL. SQLite may be supported for local development but cannot be the production target.

## Azure Architecture

Current production baseline:

```text
Subscription: Azure subscription 1
Tenant: Zambezi Rising
Resource group: iyam-b2c-prod-rg
Region: East US 2
App Service plan: iyam-b2c-prod-plan
App Service: ubuntu-20260510
PostgreSQL server: ubuntu-20260510-pg
PostgreSQL database: funeralfund
Default hostname: ubuntu-20260510.azurewebsites.net
Custom hostname: ubuntu.zambeziblue.com
```

Required Azure resources:

* Linux Azure App Service, Python 3.12 runtime
* Azure Database for PostgreSQL Flexible Server, PostgreSQL 16 or newer
* App Service application settings for runtime configuration
* HTTPS-only enabled
* Custom domain binding
* Managed certificate for custom domain after DNS validation
* Azure Monitor and App Service logs enabled

Recommended future resources:

* Azure Key Vault for secrets
* Azure Blob Storage for payment proof and branding assets
* Application Insights for request tracing and exceptions
* Redis-compatible broker if Celery background jobs are enabled

PostgreSQL firewall:

* Allow Azure services to reach the server.
* Prefer private networking for v2 production hardening when the network topology is ready.

## App Service Startup

The App Service must:

1. Load the deployed package.
2. Install Python dependencies.
3. Run database migrations.
4. Start Gunicorn.

Required startup behavior:

```bash
flask --app funeral_fund:create_app db upgrade
gunicorn --bind=0.0.0.0:${PORT:-8000} --workers=2 --timeout=120 'funeral_fund:create_app()'
```

The current deployment stores a base64 startup script in `PAMODZI_STARTUP_B64` and uses this App Service startup command:

```bash
bash -lc "echo \"$PAMODZI_STARTUP_B64\" | base64 -d > /tmp/pamodzi-startup.sh && chmod +x /tmp/pamodzi-startup.sh && exec /tmp/pamodzi-startup.sh"
```

V2 may replace this with a committed startup script or container image, but the migration-before-serving behavior must remain.

## GitHub Requirements

The repository must be hosted on GitHub and managed through normal PR review.

Required branch model:

* `main`: production-ready branch
* feature branches: short-lived implementation branches
* protected `main`: require PR review and passing checks

Required local `gh` workflow:

```bash
gh auth status
gh repo view
gh pr create --draft --base main --head <branch>
gh pr checks --watch
gh pr view --web
```

Required GitHub repository secrets or environment secrets:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP=iyam-b2c-prod-rg
AZURE_WEBAPP_NAME=ubuntu-20260510
OIDC_CLIENT_ID
OIDC_CLIENT_SECRET
SECRET_KEY
DATABASE_URL
```

Prefer GitHub Actions OIDC federation to long-lived Azure publish profiles. If publish profiles are used temporarily, they must be stored as environment-scoped secrets and rotated after migration to OIDC federation.

## CI/CD Pipeline

V2 must include `.github/workflows/ci.yml`.

PR validation jobs:

* Check out code.
* Set up Python 3.12.
* Install dependencies.
* Run tests with `.venv/bin/pytest` or equivalent.
* Run migration smoke test against SQLite or ephemeral PostgreSQL.
* Upload test results when available.

Production deployment job:

* Trigger on merge to `main`.
* Require the `production` GitHub environment.
* Log into Azure using GitHub OIDC.
* Package source from the merge commit.
* Deploy to App Service.
* Apply or verify required app settings.
* Restart the App Service.
* Call `GET /readyz`.

Reference workflow shape:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m venv .venv
      - run: .venv/bin/pip install -r requirements.txt
      - run: .venv/bin/pytest

  deploy:
    if: github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: production
    env:
      AZURE_RESOURCE_GROUP: ${{ vars.AZURE_RESOURCE_GROUP }}
      AZURE_WEBAPP_NAME: ${{ vars.AZURE_WEBAPP_NAME }}
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: git archive --format zip HEAD -o app.zip
      - run: az webapp deployment source config-zip -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_WEBAPP_NAME" --src app.zip --timeout 900
      - run: az webapp restart -g "$AZURE_RESOURCE_GROUP" -n "$AZURE_WEBAPP_NAME"
      - run: curl -fsS "https://${AZURE_WEBAPP_NAME}.azurewebsites.net/readyz"
```

The final workflow should move non-secret deployment constants to repository or environment variables instead of secrets where possible.

## Infrastructure Re-Creation Procedure

Use the Azure CLI from the project virtualenv if installed there:

```bash
source .venv/bin/activate
az account show
```

Create PostgreSQL:

```bash
az postgres flexible-server create \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510-pg \
  -l eastus2 \
  --version 16 \
  --tier Burstable \
  --sku-name Standard_B1ms \
  --storage-size 32 \
  --storage-auto-grow Enabled \
  --backup-retention 7 \
  --admin-user ffadmin \
  --public-access 0.0.0.0

az postgres flexible-server db create \
  -g iyam-b2c-prod-rg \
  -s ubuntu-20260510-pg \
  -d funeralfund
```

Create App Service:

```bash
az webapp create \
  -g iyam-b2c-prod-rg \
  -p iyam-b2c-prod-plan \
  -n ubuntu-20260510 \
  --runtime "PYTHON:3.12"

az webapp update \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510 \
  --https-only true
```

Deploy:

```bash
git archive --format zip HEAD -o /tmp/funeralfund.zip
az webapp deployment source config-zip \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510 \
  --src /tmp/funeralfund.zip \
  --timeout 900
curl -fsS https://ubuntu-20260510.azurewebsites.net/readyz
```

Custom domain:

```bash
az webapp config hostname add \
  -g iyam-b2c-prod-rg \
  --webapp-name ubuntu-20260510 \
  --hostname ubuntu.zambeziblue.com
```

DNS must point:

```text
ubuntu.zambeziblue.com CNAME ubuntu-20260510.azurewebsites.net
```

After DNS resolves to the new app:

```bash
az webapp config ssl create \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510 \
  --hostname ubuntu.zambeziblue.com \
  --certificate-name ubuntu.zambeziblue.com-ubuntu-20260510
```

Then bind the certificate with SNI:

```bash
THUMBPRINT=$(az webapp config ssl show \
  -g iyam-b2c-prod-rg \
  --certificate-name ubuntu.zambeziblue.com-ubuntu-20260510 \
  --query thumbprint -o tsv)

az webapp config ssl bind \
  -g iyam-b2c-prod-rg \
  -n ubuntu-20260510 \
  --certificate-thumbprint "$THUMBPRINT" \
  --ssl-type SNI
```

## Security Requirements

V2 must enforce:

* HTTPS-only in production
* Secure session cookies in production
* CSRF protection for mutating web form requests
* Role checks for all leadership and admin operations
* Audit logging for mutating operations
* No production header-auth fallback
* Secret rotation capability
* Database migrations reviewed in PRs
* Least-privilege Azure and GitHub credentials

## Operational Checks

Required post-deployment checks:

```bash
curl -fsS https://ubuntu-20260510.azurewebsites.net/readyz
az webapp show -g iyam-b2c-prod-rg -n ubuntu-20260510 --query "{state:state,httpsOnly:httpsOnly,defaultHostName:defaultHostName}"
az postgres flexible-server show -g iyam-b2c-prod-rg -n ubuntu-20260510-pg --query "{state:state,fullyQualifiedDomainName:fullyQualifiedDomainName,version:version}"
```

Expected results:

* App Service state is `Running`.
* HTTPS-only is `true`.
* `/readyz` returns `{"status":"ok"}`.
* PostgreSQL state is `Ready`.

## V2 Acceptance Criteria

V2 is complete when:

* A clean clone can run locally from README instructions.
* Tests pass in GitHub Actions on PRs.
* Main branch deploys to Azure App Service automatically.
* App Service runs migrations before serving traffic.
* OIDC login works through ZambeziBlue IAM.
* PostgreSQL is the production database.
* Custom domain and managed TLS are configured.
* `gh` can be used for normal PR creation, review, checks, and release workflow.
* No committed file contains production secrets.
