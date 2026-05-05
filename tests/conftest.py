from __future__ import annotations

import pytest

from funeral_fund import create_app
from funeral_fund.config import Config
from funeral_fund.extensions import db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    FUNERAL_FUND_ENV = "testing"
    WEB_CSRF_ENABLED = False


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_headers():
    return {
        "X-User-Email": "admin@example.test",
        "X-User-Name": "Admin",
        "X-User-Groups": "admin",
    }


@pytest.fixture()
def leader_headers():
    return {
        "X-User-Email": "leader@example.test",
        "X-User-Name": "Leader",
        "X-User-Groups": "Community_leader",
    }


@pytest.fixture()
def member_headers():
    return {
        "X-User-Email": "member@example.test",
        "X-User-Name": "Member",
        "X-User-Groups": "community_member",
    }
