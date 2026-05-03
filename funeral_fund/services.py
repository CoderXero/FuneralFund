from __future__ import annotations

import json
from datetime import date

from dateutil.relativedelta import relativedelta

from .extensions import db
from .models import AuditLog, FamilyMember, Payment, User, utcnow


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
        if age_on(dependant.dob, today) is not None and age_on(dependant.dob, today) >= 21:
            dependant.category = "pending_member"
            dependant.status = "pending"
            converted.append(dependant)
            audit(None, "family.age_out", "family_member", dependant.id, name=dependant.name)
    return converted
