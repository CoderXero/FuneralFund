from __future__ import annotations

from flask_migrate import upgrade
from sqlalchemy import inspect

from funeral_fund import create_app
from funeral_fund.config import Config
from funeral_fund.extensions import db


def test_migrations_upgrade_to_head(tmp_path):
    class MigrationConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migration.db'}"
        FUNERAL_FUND_ENV = "testing"
        WEB_CSRF_ENABLED = False

    app = create_app(MigrationConfig)
    with app.app_context():
        upgrade(directory="migrations")
        inspector = inspect(db.engine)

    columns = {column["name"] for column in inspector.get_columns("family_members")}
    assert "email" in columns
    assert "converted_user_id" in columns
