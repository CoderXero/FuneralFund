from __future__ import annotations

import json
from datetime import date

from dateutil.relativedelta import relativedelta

from .extensions import db
from .models import AuditLog, FamilyMember, Payment, User, utcnow


ROLES = {"admin", "community_admin", "community_user"}
STATUSES = {"active", "pending", "late", "suspended"}
FAMILY_CATEGORIES = {"primary", "secondary", "dependant", "relative", "pending_member"}
FEE_TYPES = {"one_time", "recurring"}
RECURRING_INTERVALS = {"", "monthly", "yearly"}
PAYMENT_METHODS = {"cashapp", "venmo", "zelle", "manual"}
MESSAGE_AUDIENCES = {"all", "community_user", "community_admin", "leadership"}


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("email must be a valid email address")
    return normalized


def age_on(dob: date | None, today: date | None = None) -> int | None:
    if dob is None:
        return None
    today = today or date.today()
    return relativedelta(today, dob).years


def membership_status(days_overdue: int) -> str:
    if days_overdue <= 30:
        return "active"
    if days_overdue <= 60:
        return "late"
    return "suspended"


def validate_choice(value: str, field: str, choices: set[str]) -> None:
    if value not in choices:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(choices))}")


def ensure_role_assignment_allowed(actor: User, role: str) -> None:
    validate_choice(role, "role", ROLES)
    if role == "admin" and not actor.is_admin:
        raise PermissionError("only admins can assign the admin role")


def audit(actor: User | None, action: str, target_type: str, target_id: object, **metadata) -> None:
    db.session.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def approve_member(member: User, actor: User) -> User:
    member.status = "active"
    audit(actor, "member.approve", "user", member.id)
    return member


def promote_member(member: User, actor: User, **metadata) -> User:
    if member.role == "admin" and not actor.is_admin:
        raise PermissionError("only admins can change admin members")
    if member.role != "community_user":
        raise ValueError("only community members can be promoted")
    member.role = "community_admin"
    audit(actor, "member.promote", "user", member.id, **metadata)
    return member


def verify_payment(payment: Payment, actor: User, status: str) -> Payment:
    if status not in {"verified", "rejected"}:
        raise ValueError("payment status must be verified or rejected")
    payment.status = status
    payment.verified_by_id = actor.id
    payment.verified_at = utcnow()
    audit(actor, f"payment.{status}", "payment", payment.id)
    return payment


def age_out_dependants(today: date | None = None) -> list[FamilyMember]:
    today = today or date.today()
    converted: list[FamilyMember] = []
    dependants = FamilyMember.query.filter_by(category="dependant", status="active").all()
    for dependant in dependants:
        dependant_age = age_on(dependant.dob, today)
        if dependant_age is None or dependant_age < 21:
            continue
        dependant.category = "pending_member"
        dependant.status = "pending"
        if dependant.converted_user_id is None:
            email = normalize_email(dependant.email) if dependant.email else f"pending-family-{dependant.id}@pending.local"
            user = User.query.filter_by(email=email).one_or_none()
            if user is None:
                user = User(
                    email=email,
                    name=dependant.name,
                    role="community_user",
                    status="pending",
                    dob=dependant.dob,
                )
                db.session.add(user)
                db.session.flush()
            dependant.converted_user_id = user.id
        converted.append(dependant)
        audit(
            None,
            "family.age_out",
            "family_member",
            dependant.id,
            name=dependant.name,
            converted_user_id=dependant.converted_user_id,
        )
    return converted
