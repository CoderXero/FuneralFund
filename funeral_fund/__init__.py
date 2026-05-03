from __future__ import annotations

from pathlib import Path

from flask import Flask

from .config import Config
from .extensions import db, migrate, oauth


def create_app(config_object: type[Config] | None = None) -> Flask:
    root_dir = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root_dir / "templates"))
    app.config.from_object(config_object or Config)

    db.init_app(app)
    migrate.init_app(app, db)
    oauth.init_app(app)
    oauth.register(
        name="oidc",
        client_id=app.config["CLIENT_ID"],
        client_secret=app.config["CLIENT_SECRET"],
        server_metadata_url=app.config["OIDC_OPENID_CONFIG_URL"],
        client_kwargs={
            "scope": app.config["OIDC_SCOPE"],
            "code_challenge_method": app.config["OIDC_CODE_CHALLENGE_METHOD"],
        },
    )

    from .auth import auth_bp
    from .api import api_bp
    from .web import web_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create database tables for local development."""
        db.create_all()
        print("Database initialized.")

    return app
