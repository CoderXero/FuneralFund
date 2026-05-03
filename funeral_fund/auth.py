from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from flask import abort, current_app, g, request

from .extensions import db
from .models import User

F = TypeVar("F", bound=Callable)


GROUP_ROLE_MAP = {
    "admin": "admin",
    "community_leader": "leader",
    "community_user": "member",
}


def role_from_groups(groups: list[str]) -> str:
    for group, role in GROUP_ROLE_MAP.items():
        if group in groups:
            return role
    return "member"


def current_user() -> User:
    email = request.headers.get("X-User-Email")
    name = request.headers.get("X-User-Name")
    groups = [
        group.strip()
        for group in request.headers.get("X-User-Groups", "").split(",")
        if group.strip()
    ]

    if not email and current_app.config["FUNERAL_FUND_ENV"] == "development":
        email = current_app.config["DEFAULT_ADMIN_EMAIL"]
        name = current_app.config["DEFAULT_ADMIN_NAME"]
        groups = ["admin"]

    if not email:
        abort(401)

    user = User.query.filter_by(email=email).one_or_none()
    if user is None:
        user = User(
            email=email,
            name=name or email,
            role=role_from_groups(groups),
            status="active" if "admin" in groups else "pending",
        )
        db.session.add(user)
        db.session.commit()
    elif groups:
        user.role = role_from_groups(groups)
        db.session.commit()

    g.current_user = user
    return user


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
