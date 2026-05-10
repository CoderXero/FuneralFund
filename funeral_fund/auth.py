from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, abort, current_app, g, redirect, request, session, url_for

from .extensions import db, oauth
from .models import User
from .services import normalize_email

F = TypeVar("F", bound=Callable)
auth_bp = Blueprint("auth", __name__)


GROUP_ROLE_MAP = {
    "admin": "admin",
    "community_leader": "community_admin",
    "community_admin": "community_admin",
    "community_member": "community_user",
    "community_user": "community_user",
}


def role_from_groups(groups: list[str] | tuple[str, ...]) -> str:
    normalized_groups = {group.lower() for group in groups}
    for group, role in GROUP_ROLE_MAP.items():
        if group in normalized_groups:
            return role
    return "community_user"


def header_auth_allowed() -> bool:
    return current_app.config["FUNERAL_FUND_ENV"] in {"development", "testing"}


def redirect_uri() -> str:
    if current_app.config["FUNERAL_FUND_ENV"] == "development":
        return current_app.config["LOCAL_REDIRECT_URI"]
    return current_app.config["REDIRECT_URI"]


def ensure_oauth_configured() -> None:
    if not current_app.config["CLIENT_ID"]:
        abort(503, "OAuth CLIENT_ID is not configured")
    if not current_app.config["CLIENT_SECRET"]:
        abort(503, "OAuth CLIENT_SECRET is not configured")


def normalize_groups(groups: Any) -> list[str]:
    if groups is None:
        return []
    if isinstance(groups, str):
        return [group.strip() for group in groups.split(",") if group.strip()]
    return [str(group).strip() for group in groups if str(group).strip()]


def upsert_user(
    *,
    email: str,
    name: str | None,
    groups: list[str],
    idp_sub: str | None = None,
) -> User:
    email = normalize_email(email)
    user = User.query.filter_by(email=email).one_or_none()
    role = role_from_groups(groups)
    if user is None:
        user = User(
            email=email,
            name=name or email,
            role=role,
            status="active" if role == "admin" else "pending",
            idp_sub=idp_sub,
        )
        db.session.add(user)
    else:
        user.name = name or user.name
        user.role = role
        if idp_sub:
            user.idp_sub = idp_sub
    db.session.commit()
    return user


def user_from_development_headers() -> User | None:
    if not header_auth_allowed():
        return None

    email = request.headers.get("X-User-Email")
    name = request.headers.get("X-User-Name")
    groups = normalize_groups(request.headers.get("X-User-Groups"))

    if not email:
        return None

    return upsert_user(email=email, name=name, groups=groups)


def current_user() -> User:
    user = user_from_development_headers()
    if user is None and session.get("user_id"):
        user = db.session.get(User, session["user_id"])

    if user is None:
        abort(401)

    g.current_user = user
    return user


def login_required(func: F) -> F:
    @wraps(func)
    def wrapper(*args, **kwargs):
        current_user()
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_roles(*roles: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user.role not in roles:
                abort(403)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


@auth_bp.get("/login")
def login():
    ensure_oauth_configured()
    return oauth.oidc.authorize_redirect(redirect_uri())


@auth_bp.get("/callback")
def callback():
    ensure_oauth_configured()
    try:
        token = oauth.oidc.authorize_access_token()
    except OAuthError as exc:
        description = exc.description or exc.error or "OAuth provider rejected the login callback"
        abort(502, description)
    userinfo = token.get("userinfo") or oauth.oidc.userinfo(token=token)
    email = userinfo.get("email")
    if not email:
        abort(400, "OIDC response did not include an email claim")

    groups = normalize_groups(userinfo.get("groups") or userinfo.get("roles"))
    user = upsert_user(
        email=email,
        name=userinfo.get("name") or userinfo.get("preferred_username"),
        groups=groups,
        idp_sub=userinfo.get("sub"),
    )
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    return redirect(url_for("web.dashboard"))


@auth_bp.post("/logout")
@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.landing_page"))
