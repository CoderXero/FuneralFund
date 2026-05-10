from __future__ import annotations

from funeral_fund import create_app
from funeral_fund.config import Config
from funeral_fund.csrf import CSRF_SESSION_KEY
from funeral_fund.extensions import db, oauth
from funeral_fund.models import User


class ProductionConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    FUNERAL_FUND_ENV = "production"
    SECRET_KEY = "test-secret"
    CLIENT_SECRET = "test-client-secret"


def test_production_ignores_development_auth_headers():
    app = create_app(ProductionConfig)
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        response = client.get(
            "/api/members",
            headers={
                "X-User-Email": "spoof@example.test",
                "X-User-Groups": "admin",
            },
        )

    assert response.status_code == 401


def test_development_does_not_create_default_admin_without_idp_or_headers():
    class DevelopmentConfig(ProductionConfig):
        FUNERAL_FUND_ENV = "development"

    app = create_app(DevelopmentConfig)
    with app.app_context():
        db.create_all()

    with app.test_client() as client:
        response = client.get("/dashboard")

    assert response.status_code == 401
    with app.app_context():
        assert User.query.count() == 0


def test_oauth_callback_creates_session(monkeypatch):
    app = create_app(ProductionConfig)
    with app.app_context():
        db.create_all()

    class FakeOidc:
        def authorize_access_token(self):
            return {
                "userinfo": {
                    "sub": "idp-123",
                    "email": "leader@example.test",
                    "name": "Leader",
                    "groups": ["Community_leader"],
                }
            }

    monkeypatch.setattr("funeral_fund.auth.oauth.oidc", FakeOidc(), raising=False)

    with app.test_client() as client:
        response = client.get("/auth/callback")
        with client.session_transaction() as session:
            user_id = session["user_id"]

    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user is not None
        assert user.email == "leader@example.test"
        assert user.role == "community_admin"


def test_group_claims_map_to_app_roles():
    from funeral_fund.auth import role_from_groups

    assert role_from_groups(["admin"]) == "admin"
    assert role_from_groups(["Community_leader"]) == "community_admin"
    assert role_from_groups(["community_member"]) == "community_user"


def test_development_header_auth_normalizes_email(client):
    response = client.get(
        "/dashboard",
        headers={
            "X-User-Email": " Member@Example.Test ",
            "X-User-Name": "Member",
            "X-User-Groups": "community_member",
        },
    )

    assert response.status_code == 200
    with client.application.app_context():
        assert User.query.filter_by(email="member@example.test").one()


def test_oauth_login_requires_client_secret():
    class MissingSecretConfig(ProductionConfig):
        CLIENT_SECRET = ""

    app = create_app(MissingSecretConfig)
    with app.test_client() as client:
        response = client.get("/auth/login")

    assert response.status_code == 503
    assert b"CLIENT_SECRET" in response.data


def test_oauth_client_uses_pkce_s256():
    app = create_app(ProductionConfig)

    with app.app_context():
        assert oauth.oidc.client_kwargs["code_challenge_method"] == "S256"


def test_logout_clears_session():
    app = create_app(ProductionConfig)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 123
            session[CSRF_SESSION_KEY] = "known-token"

        response = client.post("/auth/logout", data={"csrf_token": "known-token"})

        with client.session_transaction() as session:
            assert "user_id" not in session

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_web_post_requires_csrf_token():
    app = create_app(ProductionConfig)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 123
            session[CSRF_SESSION_KEY] = "known-token"

        response = client.post("/auth/logout")

    assert response.status_code == 400
    assert b"CSRF" in response.data


def test_web_post_accepts_valid_csrf_token():
    app = create_app(ProductionConfig)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 123
            session[CSRF_SESSION_KEY] = "known-token"

        response = client.post("/auth/logout", data={"csrf_token": "known-token"})

        with client.session_transaction() as session:
            assert "user_id" not in session

    assert response.status_code == 302
