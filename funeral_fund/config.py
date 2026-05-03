from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///funeral_fund.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FUNERAL_FUND_ENV = os.getenv("FUNERAL_FUND_ENV", "development")
    DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.test")
    DEFAULT_ADMIN_NAME = os.getenv("DEFAULT_ADMIN_NAME", "Local Admin")
    CLIENT_ID = os.getenv("CLIENT_ID", "pamodzi_cc")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
    REDIRECT_URI = os.getenv("REDIRECT_URI", "https://iam.zambeziblue.com/callback")
    LOCAL_REDIRECT_URI = os.getenv("LOCAL_REDIRECT_URI", "http://localhost:8003/auth/callback")
    OIDC_OPENID_CONFIG_URL = os.getenv(
        "OIDC_OPENID_CONFIG_URL",
        "https://iam.zambeziblue.com/.well-known/openid-configuration",
    )
    JWKS_URL = os.getenv("JWKS_URL", "https://iam.zambeziblue.com/.well-known/jwks.json")
    SIGNUP_URL = os.getenv("SIGNUP_URL", "https://iam.zambeziblue.com/signup")
    SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "2555"))
