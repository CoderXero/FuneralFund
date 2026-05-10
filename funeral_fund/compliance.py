from __future__ import annotations

import json
from datetime import timedelta

from .extensions import db
from .models import AuditLog, FamilyMember, Message, Payment, Setting, User, utcnow
from .services import audit


def export_user_data(user: User) -> dict:
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "status": user.status,
            "dob": user.dob.isoformat() if user.dob else None,
        },
        "family_members": [
            {
                "id": family.id,
                "name": family.name,
                "email": family.email,
                "category": family.category,
                "relationship": family.relationship,
                "dob": family.dob.isoformat() if family.dob else None,
                "status": family.status,
            }
            for family in FamilyMember.query.filter_by(user_id=user.id).all()
        ],
        "payments": [
            {
                "id": payment.id,
                "method": payment.method,
                "amount": str(payment.amount),
                "status": payment.status,
                "created_at": payment.created_at.isoformat(),
            }
            for payment in Payment.query.filter_by(member_id=user.id).all()
        ],
        "messages": [
            {
                "id": message.id,
                "audience": message.audience,
                "subject": message.subject,
                "created_at": message.created_at.isoformat(),
            }
            for message in Message.query.filter(
                (Message.sender_id == user.id) | (Message.recipient_id == user.id)
            ).all()
        ],
        "settings": {
            setting.key: setting.value
            for setting in Setting.query.filter(Setting.key.startswith(f"user_{user.id}_")).all()
        },
    }


def anonymize_user(user: User, actor: User) -> User:
    original_id = user.id
    user.email = f"deleted-user-{user.id}@deleted.local"
    user.name = "Deleted User"
    user.idp_sub = None
    user.dob = None
    user.status = "suspended"
    for setting in Setting.query.filter(Setting.key.startswith(f"user_{user.id}_")).all():
        db.session.delete(setting)
    for message in Message.query.filter(Message.sender_id == user.id).all():
        message.sender_id = None
    audit(actor, "gdpr.user.anonymize", "user", original_id)
    return user


def purge_old_audit_logs(retention_days: int, actor: User | None = None) -> int:
    cutoff = utcnow() - timedelta(days=retention_days)
    logs = AuditLog.query.filter(AuditLog.timestamp < cutoff).all()
    count = len(logs)
    for log in logs:
        db.session.delete(log)
    if actor:
        audit(actor, "audit.retention.purge", "audit_log", "retention", count=count)
    return count


def export_user_data_json(user: User) -> str:
    return json.dumps(export_user_data(user), indent=2, sort_keys=True)
