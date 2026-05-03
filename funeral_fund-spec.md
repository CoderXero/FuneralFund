# FuneralFund — Full System Specification

## Version

1.1.0

## Solution Name

**FuneralFund** (default; branding configurable by leadership)

---

# 0. Implementation Baseline

This repository implements a Flask-based MVP that keeps the production architecture intact while providing a runnable local application.

## MVP Scope

Included in the initial implementation:

* Flask application factory
* SQLAlchemy models for users, family members, fees, notices, payments, votes, settings, and audit logs
* SQLite local development database with PostgreSQL-compatible SQLAlchemy models
* Jinja2 dashboard and management pages
* JSON API endpoints for members, family, fees, payments, voting, reports, and settings
* Role and status checks for protected operations
* Manual payment proof workflow
* Scheduled-job-ready dependant age-out service
* Pytest coverage for core lifecycle rules and API behavior

Deferred production integrations:

* Live OIDC token exchange and JWKS validation
* Live payment provider APIs
* WhatsApp provider integration
* Azure Blob Storage uploads
* Azure Key Vault secret loading
* PDF/XLSX report generation
* Celery worker deployment

Deferred integrations must be represented by explicit service boundaries so they can be enabled without changing route contracts.

## Local Development Defaults

Local variables are defined in `.env` and documented in `.env.example`.

```env
FLASK_APP=funeral_fund:create_app
FUNERAL_FUND_ENV=development
DATABASE_URL=sqlite:///funeral_fund.db
SECRET_KEY=dev-secret-change-me
DEFAULT_ADMIN_EMAIL=admin@example.test
DEFAULT_ADMIN_NAME=Local Admin
CLIENT_ID=pamodzi_cc
CLIENT_SECRET=
REDIRECT_URI=https://iam.zambeziblue.com/callback
LOCAL_REDIRECT_URI=http://localhost:8003/auth/callback
OIDC_OPENID_CONFIG_URL=https://iam.zambeziblue.com/.well-known/openid-configuration
JWKS_URL=https://iam.zambeziblue.com/.well-known/jwks.json
SIGNUP_URL=https://iam.zambeziblue.com/signup
```

Local authentication uses development headers for testing:

* `X-User-Email`
* `X-User-Name`
* `X-User-Groups`

When those headers are absent, the app creates a default local sys admin for development only.

## Authorization Rules

All mutating leadership routes require either `admin` or `community_leader`.

Member self-service routes require an authenticated active or pending member. Voting requires:

* status = `active`
* role = `member` or higher
* age >= 21
* exactly one vote per vote event

## Payment Verification Rules

Payment records begin as `pending`. Leadership can mark payment proof as:

* `verified`
* `rejected`

Verified recurring membership payments may activate a pending member when leadership approves the member.

## Data Retention And Audit

Every mutating endpoint writes an audit log with:

* actor user id
* action
* target type
* target id
* JSON metadata
* timestamp

GDPR deletion is implemented as a service boundary in the MVP and requires an admin role before production activation.

---

# 1. Executive Summary

FuneralFund is a diaspora community management platform designed for funeral assistance groups, community associations, and membership-driven financial support organizations.

The platform enables:

* Secure OAuth2/OIDC authentication via ZambeziBlue IAM
* Leadership-controlled member approval
* Membership fee and donation tracking
* Family/dependant lifecycle management
* Voting and governance
* Financial reports
* Branding customization
* WhatsApp + in-app notifications
* Azure App Services deployment
* RESTful Python 3 architecture with Jinja2 frontend

---

# 2. Core Technology Stack

## Backend

* Python 3.12+
* Flask (recommended for REST + Jinja2 simplicity)
* Flask-Jinja2 Templates
* Flask-RESTX / Flask Blueprint APIs
* SQLAlchemy ORM
* Alembic migrations
* Celery + Redis (scheduled jobs)
* PostgreSQL (Azure Database for PostgreSQL)

## Frontend

* Jinja2
* Bootstrap 5
* HTMX (optional dynamic enhancement)

## Authentication

* OAuth2 / OpenID Connect
* JWT validation using:

  * OpenID Config: `https://iam.zambeziblue.com/.well-known/openid-configuration`
  * JWKS: `https://iam.zambeziblue.com/.well-known/jwks.json`

## Deployment

* Azure App Services (Linux)
* Azure PostgreSQL
* Azure Blob Storage (proof uploads, branding assets)
* Azure Key Vault

## CI/CD

* GitHub Actions
* Azure CLI (`az`)

---

# 3. Identity & Access Management (IAM)

## Groups

### Sys Admin

**IDP Group:** `admin`

Permissions:

* Full system access
* Override leadership
* Manage global settings
* Manage deployment settings
* Manage IDP promotion API settings
* View all audit logs
* GDPR deletion execution

### Leadership

**IDP Group:** `community_leader`

Permissions:

* Approve members
* Promote members to leadership
* Trigger IDP group promotion REST API
* Configure fees
* Configure branding
* Manage voting
* Approve payouts
* Reports

### Member

**IDP Group:** `community_user`

Permissions:

* Register family
* Manage dependants/relatives
* Pay fees
* Vote (if age >= 21 and active)
* Upload payment proof

### Pending Dependant Converted Member

* Auto-created at age 21
* Requires leadership approval
* No voting until approved

---

# 4. OAuth2 / OIDC Flow

## Config

```env
CLIENT_ID=pamodzi_cc
CLIENT_SECRET=<stored in KeyVault>
REDIRECT_URI=https://iam.zambeziblue.com/callback
LOCAL_REDIRECT_URI=http://localhost:8003/auth/callback
JWKS_URL=https://iam.zambeziblue.com/.well-known/jwks.json
SIGNUP_URL=https://iam.zambeziblue.com/signup
```

## Login Flow

1. User clicks Login
2. Redirect to authorization endpoint
3. If no account → redirect to signup
4. After signup → login
5. Exchange code for token
6. Validate JWT
7. Extract claims:

   * sub
   * email
   * name
   * groups
   * exp
8. Create/update local user profile
9. Assign RBAC

---

# 5. User Lifecycle

## Member Registration

* IDP sign-in
* Profile created
* Status = Pending Approval
* Membership fee invoice generated
* Payment required
* Leadership reviews payment
* Status = Active

## Suspension Rules

### Settings Defaults:

* Grace period: 90 days
* Late threshold: 30 days
* Suspension threshold: 60 days

### Logic:

* 0–30 days overdue → Active
* 31–60 days overdue → Late
* 61+ days overdue → Suspended

---

# 6. Family Structure

## Categories

### Primary

Main member

### Secondary

One spouse maximum

### Dependant

Children under 21

### Relative

Extended relatives:

* Mother
* Father
* Aunt
* Uncle
* Other configurable

## Age-out Process

Scheduled daily job:

* Detect dependants turning 21
* Convert to Pending Full Member
* Notify leadership
* Require approval

---

# 7. Payment System

## Payment Types

### Recurring Fees

* Monthly
* Quarterly
* Yearly
* Custom intervals

### One-Time Fees

* Funeral donations
* Emergency requests
* Community events
* Notice number required

### Payouts

* Leadership-defined
* Assigned to one member
* Approval workflow

---

## Payment Methods

### Supported

* Cash App
* Zelle
* Venmo

## Payment Modes

### API Integration

When provider supports APIs

### Payment Link / QR

Generate:

* QR code
* Deep link
* Payment reference

### Manual Proof

Members upload:

* Screenshot
* Transaction ID
* Notes

Leadership verifies.

---

# 8. Voting System

## Rules

* Named votes
* One vote per active member age 21+
* Leadership defines:

  * Title
  * Description
  * Open date
  * Close date
  * Options

## Outcome

* Simple majority
* No quorum

## Reports

### Anonymous Report

Totals only

### Named Report

Member + vote choice

---

# 9. Reporting System

## Reports

### Monthly

* Revenue
* Outstanding balances
* New members
* Suspensions

### Yearly

* Fiscal summary
* Custom fiscal start/end
* Donations
* Payouts
* Audit summary

### Payment Reports

* Per member
* Per notice
* Per recurring fee

### Voter Roll

* Eligible members
* Active members
* Suspended members

## Export Formats

* PDF
* CSV
* XLSX

---

# 10. Branding Engine

Leadership configurable:

* Solution name
* Logo
* Color palette
* Custom domain
* Email templates
* PDF headers
* WhatsApp templates

Default:
**FuneralFund**

---

# 11. Settings Center

Centralized settings page includes:

## Financial

* Grace period
* Late fees
* Suspension days
* Fiscal year dates

## IAM

* Client credentials
* Promotion API endpoint
* Group mappings

## Branding

* Name/logo/colors

## Notifications

* WhatsApp API settings
* In-app templates

## Security

* Session timeout
* MFA toggle
* Audit retention

---

# 12. REST API Specification

## Authentication

### GET /auth/login

### GET /auth/callback

### POST /auth/logout

## Members

### GET /api/members

### POST /api/members

### GET /api/members/{id}

### PUT /api/members/{id}

### POST /api/members/{id}/approve

### POST /api/members/{id}/promote

### POST /api/members/{id}/suspend

## Family

### POST /api/members/{id}/family

### PUT /api/family/{family_id}

### DELETE /api/family/{family_id}

## Fees

### POST /api/fees/recurring

### POST /api/fees/one-time

### GET /api/notices/{notice_number}

## Payments

### POST /api/payments/initiate

### POST /api/payments/proof

### POST /api/payments/verify

## Voting

### POST /api/votes

### POST /api/votes/{id}/cast

### GET /api/votes/{id}/results

## Reports

### GET /api/reports/monthly

### GET /api/reports/yearly

### GET /api/reports/voter-roll

## Settings

### GET /api/settings

### PUT /api/settings

---

# 13. Database Schema (High-Level)

## Tables

### users

* id
* idp_sub
* role
* status
* created_at

### family_members

* user_id
* category
* dob
* relationship

### fees

* type
* amount
* recurring_interval

### notices

* notice_number
* amount
* due_date

### payments

* member_id
* fee_id
* method
* amount
* proof_url
* verified_by

### votes

* title
* open_date
* close_date

### vote_options

### vote_casts

### settings

### audit_logs

* actor
* action
* target
* timestamp

---

# 14. Security Requirements

## Mandatory

* JWT validation
* Role enforcement
* CSRF protection
* Rate limiting
* Azure Key Vault secrets
* Encrypted uploads
* HTTPS only
* Audit logging
* GDPR deletion

---

# 15. Jinja2 Template Structure

```txt
templates/
 ┣ base.html
 ┣ dashboard.html
 ┣ auth/
 ┃ ┣ login.html
 ┃ ┗ callback.html
 ┣ members/
 ┣ payments/
 ┣ voting/
 ┣ reports/
 ┣ settings/
 ┗ branding/
```

---

# 16. GitHub Repository Structure

```txt
funeralfund/
 ┣ app/
 ┣ templates/
 ┣ static/
 ┣ migrations/
 ┣ tests/
 ┣ postman/
 ┣ .github/workflows/
 ┣ Dockerfile
 ┣ requirements.txt
 ┗ README.md
```

---

# 17. GitHub Actions CI/CD Pipeline

## Pipeline Stages

### PR Validation

* Lint (flake8)
* Unit tests (pytest)
* Security scan (bandit)

### Build

* Docker build
* Package artifact

### Deploy

```yaml
az login
az webapp deploy
az postgres flexible-server
```

## Environments

* dev
* staging
* production

---

# 18. Azure Deployment Architecture

## Components

* Azure App Service
* Azure PostgreSQL
* Azure Blob Storage
* Azure Key Vault
* Azure Monitor
* Azure Application Insights

---

# 19. Postman Collection

## Includes

* OAuth token acquisition
* Environment variables
* Full CRUD
* Tests
* Pre-request scripts
* Admin workflows
* Voting scenarios
* Payment scenarios

---

# 20. Compliance

## GDPR

* Export user data
* Delete user data
* Audit retention policy

## Audit

All changes immutable.

---

# 21. Future Enhancements

* Mobile app
* SMS integration
* Multi-community tenancy
* Stripe fallback
* AI fraud detection

---

# 22. Success Criteria

The platform is complete when:

* OAuth works end-to-end
* Members register
* Leadership approves
* Payments tracked
* Voting operational
* Reports export
* Azure deployment automated
* Branding configurable
* Audit complete
