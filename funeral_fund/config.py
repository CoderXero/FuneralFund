from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///funeral_fund.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FUNERAL_FUND_ENV = os.getenv("FUNERAL_FUND_ENV", "development")
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "60")))
    CLIENT_ID = os.getenv("CLIENT_ID", "pamodzi_cc")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
    REDIRECT_URI = os.getenv("REDIRECT_URI", "https://iam.zambeziblue.com/callback")
    LOCAL_REDIRECT_URI = os.getenv("LOCAL_REDIRECT_URI", "http://localhost:8003/auth/callback")
    OIDC_SCOPE = os.getenv("OIDC_SCOPE", "openid email profile groups")
    OIDC_CODE_CHALLENGE_METHOD = os.getenv("OIDC_CODE_CHALLENGE_METHOD", "S256")
    OIDC_OPENID_CONFIG_URL = os.getenv(
        "OIDC_OPENID_CONFIG_URL",
        "https://iam.zambeziblue.com/.well-known/openid-configuration",
    )
    JWKS_URL = os.getenv("JWKS_URL", "https://iam.zambeziblue.com/.well-known/jwks.json")
    SIGNUP_URL = os.getenv("SIGNUP_URL", "https://iam.zambeziblue.com/signup")
    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
    WEB_CSRF_ENABLED = os.getenv("WEB_CSRF_ENABLED", "1") == "1"
    FISCAL_YEAR_END_MONTH = int(os.getenv("FISCAL_YEAR_END_MONTH", "12"))
    FISCAL_YEAR_END_DAY = int(os.getenv("FISCAL_YEAR_END_DAY", "31"))
    PAYMENT_CASHAPP_API_BASE_URL = os.getenv("PAYMENT_CASHAPP_API_BASE_URL", "")
    PAYMENT_CASHAPP_API_KEY = os.getenv("PAYMENT_CASHAPP_API_KEY", "")
    PAYMENT_CASHAPP_WEBHOOK_SECRET = os.getenv("PAYMENT_CASHAPP_WEBHOOK_SECRET", "")
    PAYMENT_VENMO_API_BASE_URL = os.getenv("PAYMENT_VENMO_API_BASE_URL", "")
    PAYMENT_VENMO_API_KEY = os.getenv("PAYMENT_VENMO_API_KEY", "")
    PAYMENT_VENMO_WEBHOOK_SECRET = os.getenv("PAYMENT_VENMO_WEBHOOK_SECRET", "")
    PAYMENT_ZELLE_API_BASE_URL = os.getenv("PAYMENT_ZELLE_API_BASE_URL", "")
    PAYMENT_ZELLE_API_KEY = os.getenv("PAYMENT_ZELLE_API_KEY", "")
    PAYMENT_ZELLE_WEBHOOK_SECRET = os.getenv("PAYMENT_ZELLE_WEBHOOK_SECRET", "")
