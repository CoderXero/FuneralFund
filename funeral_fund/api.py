from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from .auth import current_user, require_roles
from .extensions import db
from .compliance import anonymize_user, export_user_data_json, purge_old_audit_logs
from .integrations import BlobStorageClient, IntegrationNotConfigured, PaymentProviderClient, ReportExporter
from .models import FamilyMember, Fee, Notice, Payment, Setting, User, Vote, VoteCast, VoteOption
from .services import (
    FAMILY_CATEGORIES,
    PAYMENT_METHODS,
    STATUSES,
    age_on,
    approve_member,
    audit,
    ensure_role_assignment_allowed,
    normalize_email,
    promote_member,
    validate_choice,
    verify_payment,
)

api_bp = Blueprint("api", __name__)


def payload() -> dict:
    return request.get_json(silent=True) or {}


def error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def require_fields(data: dict, *fields: str) -> None:
    missing = [field for field in fields if data.get(field) is None or data.get(field) == ""]
    if missing:
        raise ValueError(f"missing required field: {', '.join(missing)}")


def parse_date(value: str | None, field: str = "date") -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def parse_decimal(value: object, field: str = "amount") -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal amount") from exc
    if amount <= 0:
        raise ValueError(f"{field} must be greater than zero")
    return amount


@api_bp.errorhandler(ValueError)
def value_error(exc: ValueError):
    return error(str(exc), 400)


@api_bp.errorhandler(PermissionError)
def permission_error(exc: PermissionError):
    return error(str(exc), 403)


@api_bp.errorhandler(IntegrityError)
def integrity_error(exc: IntegrityError):
    db.session.rollback()
    return error("request conflicts with existing data", 409)


@api_bp.errorhandler(IntegrationNotConfigured)
def integration_not_configured(exc: IntegrationNotConfigured):
    return error(str(exc), 503)


def user_json(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "status": user.status,
        "dob": user.dob.isoformat() if user.dob else None,
    }


@api_bp.get("/members")
@require_roles("admin", "community_admin")
def members_index():
    return jsonify([user_json(user) for user in User.query.order_by(User.created_at.desc()).all()])


@api_bp.post("/members")
@require_roles("admin", "community_admin")
def members_create():
    data = payload()
    require_fields(data, "email")
    actor = current_user()
    role = data.get("role", "community_user")
    status = data.get("status", "pending")
    ensure_role_assignment_allowed(actor, role)
    validate_choice(status, "status", STATUSES)
    user = User(
        email=normalize_email(data["email"]),
        name=data.get("name", data["email"]),
        role=role,
        status=status,
        dob=parse_date(data.get("dob"), "dob"),
    )
    db.session.add(user)
    db.session.flush()
    audit(actor, "member.create", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user)), 201


@api_bp.get("/members/<int:member_id>")
@require_roles("admin", "community_admin")
def members_show(member_id: int):
    return jsonify(user_json(db.get_or_404(User, member_id)))


@api_bp.put("/members/<int:member_id>")
@require_roles("admin", "community_admin")
def members_update(member_id: int):
    data = payload()
    actor = current_user()
    user = db.get_or_404(User, member_id)
    if "role" in data:
        ensure_role_assignment_allowed(actor, data["role"])
    if "status" in data:
        validate_choice(data["status"], "status", STATUSES)
    for field in ["name", "role", "status"]:
        if field in data:
            setattr(user, field, data[field])
    if "dob" in data:
        user.dob = parse_date(data["dob"], "dob")
    audit(actor, "member.update", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/approve")
@require_roles("admin", "community_admin")
def members_approve(member_id: int):
    actor = current_user()
    user = approve_member(db.get_or_404(User, member_id), actor)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/promote")
@require_roles("admin", "community_admin")
def members_promote(member_id: int):
    actor = current_user()
    user = db.get_or_404(User, member_id)
    promote_member(user, actor)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/suspend")
@require_roles("admin", "community_admin")
def members_suspend(member_id: int):
    actor = current_user()
    user = db.get_or_404(User, member_id)
    user.status = "suspended"
    audit(actor, "member.suspend", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/family")
@require_roles("admin", "community_admin", "community_user")
def family_create(member_id: int):
    actor = current_user()
    if actor.id != member_id and not actor.is_leadership:
        return jsonify({"error": "cannot modify another member family"}), 403
    data = payload()
    require_fields(data, "name", "category")
    validate_choice(
        data["category"],
        "category",
        FAMILY_CATEGORIES,
    )
    family = FamilyMember(
        user_id=member_id,
        name=data["name"],
        category=data["category"],
        relationship=data.get("relationship"),
        email=normalize_email(data["email"]) if data.get("email") else None,
        dob=parse_date(data.get("dob"), "dob"),
    )
    db.session.add(family)
    db.session.flush()
    audit(actor, "family.create", "family_member", family.id)
    db.session.commit()
    return jsonify({"id": family.id, "name": family.name, "category": family.category}), 201


@api_bp.put("/family/<int:family_id>")
@require_roles("admin", "community_admin", "community_user")
def family_update(family_id: int):
    actor = current_user()
    family = db.get_or_404(FamilyMember, family_id)
    if actor.id != family.user_id and not actor.is_leadership:
        return jsonify({"error": "cannot modify another member family"}), 403
    data = payload()
    if "category" in data:
        validate_choice(
            data["category"],
            "category",
            FAMILY_CATEGORIES,
        )
    if "status" in data:
        validate_choice(data["status"], "status", {"active", "pending", "inactive"})
    for field in ["name", "category", "relationship", "status"]:
        if field in data:
            setattr(family, field, data[field])
    if "email" in data:
        family.email = normalize_email(data["email"]) if data["email"] else None
    if "dob" in data:
        family.dob = parse_date(data["dob"], "dob")
    audit(actor, "family.update", "family_member", family.id)
    db.session.commit()
    return jsonify({"id": family.id, "name": family.name, "category": family.category})


@api_bp.delete("/family/<int:family_id>")
@require_roles("admin", "community_admin", "community_user")
def family_delete(family_id: int):
    actor = current_user()
    family = db.get_or_404(FamilyMember, family_id)
    if actor.id != family.user_id and not actor.is_leadership:
        return jsonify({"error": "cannot delete another member family"}), 403
    audit(actor, "family.delete", "family_member", family.id)
    db.session.delete(family)
    db.session.commit()
    return "", 204


@api_bp.post("/fees/recurring")
@require_roles("admin", "community_admin")
def fees_recurring_create():
    data = payload()
    require_fields(data, "name", "amount")
    fee = Fee(
        name=data["name"],
        type="recurring",
        amount=parse_decimal(data["amount"]),
        recurring_interval=data.get("recurring_interval", "monthly"),
    )
    db.session.add(fee)
    db.session.flush()
    audit(current_user(), "fee.create", "fee", fee.id, type="recurring")
    db.session.commit()
    return jsonify({"id": fee.id, "name": fee.name}), 201


@api_bp.post("/fees/one-time")
@require_roles("admin", "community_admin")
def fees_one_time_create():
    data = payload()
    require_fields(data, "name", "amount")
    fee = Fee(name=data["name"], type="one_time", amount=parse_decimal(data["amount"]))
    db.session.add(fee)
    db.session.flush()
    audit(current_user(), "fee.create", "fee", fee.id, type="one_time")
    db.session.commit()
    return jsonify({"id": fee.id, "name": fee.name}), 201


@api_bp.get("/notices/<notice_number>")
@require_roles("admin", "community_admin", "community_user")
def notices_show(notice_number: str):
    notice = Notice.query.filter_by(notice_number=notice_number).first_or_404()
    return jsonify({"notice_number": notice.notice_number, "title": notice.title, "amount": str(notice.amount)})


@api_bp.post("/payments/initiate")
@require_roles("admin", "community_admin", "community_user")
def payments_initiate():
    data = payload()
    require_fields(data, "amount")
    actor = current_user()
    try:
        member_id = int(data.get("member_id", actor.id))
    except (TypeError, ValueError) as exc:
        raise ValueError("member_id must be an integer") from exc
    if actor.id != member_id and not actor.is_leadership:
        return jsonify({"error": "cannot initiate payment for another member"}), 403
    if db.session.get(User, member_id) is None:
        return error("member not found", 404)
    validate_choice(data.get("method", "manual"), "method", PAYMENT_METHODS)
    payment = Payment(
        member_id=member_id,
        fee_id=data.get("fee_id"),
        notice_id=data.get("notice_id"),
        method=data.get("method", "manual"),
        amount=parse_decimal(data["amount"]),
    )
    db.session.add(payment)
    db.session.flush()
    audit(actor, "payment.initiate", "payment", payment.id)
    db.session.commit()
    return jsonify({"id": payment.id, "status": payment.status}), 201


@api_bp.post("/payments/proof")
@require_roles("admin", "community_admin", "community_user")
def payments_proof():
    data = payload()
    require_fields(data, "payment_id")
    actor = current_user()
    payment = db.get_or_404(Payment, data["payment_id"])
    if actor.id != payment.member_id and not actor.is_leadership:
        return jsonify({"error": "cannot upload proof for another member"}), 403
    payment.proof_url = data.get("proof_url")
    payment.transaction_id = data.get("transaction_id")
    payment.notes = data.get("notes")
    audit(actor, "payment.proof", "payment", payment.id)
    db.session.commit()
    return jsonify({"id": payment.id, "status": payment.status})


@api_bp.post("/payments/verify")
@require_roles("admin", "community_admin")
def payments_verify():
    data = payload()
    require_fields(data, "payment_id", "status")
    payment = verify_payment(db.get_or_404(Payment, data["payment_id"]), current_user(), data["status"])
    db.session.commit()
    return jsonify({"id": payment.id, "status": payment.status})


@api_bp.post("/votes")
@require_roles("admin", "community_admin")
def votes_create():
    data = payload()
    require_fields(data, "title", "open_date", "close_date")
    options = data.get("options", [])
    if not isinstance(options, list) or len([option for option in options if str(option).strip()]) < 2:
        raise ValueError("votes require at least two options")
    open_date = parse_date(data["open_date"], "open_date") or date.today()
    close_date = parse_date(data["close_date"], "close_date") or date.today()
    if close_date < open_date:
        raise ValueError("close_date must be on or after open_date")
    vote = Vote(
        title=data["title"],
        description=data.get("description"),
        open_date=open_date,
        close_date=close_date,
    )
    for option in options:
        label = str(option).strip()
        if label:
            vote.options.append(VoteOption(label=label))
    db.session.add(vote)
    db.session.flush()
    audit(current_user(), "vote.create", "vote", vote.id)
    db.session.commit()
    return jsonify({"id": vote.id, "title": vote.title}), 201


@api_bp.post("/votes/<int:vote_id>/cast")
@require_roles("admin", "community_admin", "community_user")
def votes_cast(vote_id: int):
    actor = current_user()
    data = payload()
    require_fields(data, "option_id")
    vote = db.get_or_404(Vote, vote_id)
    today = date.today()
    if not (vote.open_date <= today <= vote.close_date):
        return jsonify({"error": "vote is closed"}), 400
    actor_age = age_on(actor.dob)
    if actor.status != "active" or actor_age is None or actor_age < 21:
        return jsonify({"error": "member is not eligible to vote"}), 403
    option = VoteOption.query.filter_by(id=data["option_id"], vote_id=vote.id).one_or_none()
    if option is None:
        return error("option does not belong to this vote", 400)
    if VoteCast.query.filter_by(vote_id=vote.id, member_id=actor.id).one_or_none():
        return error("member has already voted", 409)
    cast = VoteCast(vote_id=vote.id, option_id=option.id, member_id=actor.id)
    db.session.add(cast)
    audit(actor, "vote.cast", "vote", vote.id)
    db.session.commit()
    return jsonify({"id": cast.id}), 201


@api_bp.get("/votes/<int:vote_id>/results")
@require_roles("admin", "community_admin")
def votes_results(vote_id: int):
    vote = db.get_or_404(Vote, vote_id)
    results = []
    for option in vote.options:
        total = VoteCast.query.filter_by(vote_id=vote.id, option_id=option.id).count()
        results.append({"option_id": option.id, "label": option.label, "total": total})
    return jsonify({"vote_id": vote.id, "results": results})


@api_bp.get("/reports/monthly")
@require_roles("admin", "community_admin")
def reports_monthly():
    return jsonify({
        "members": User.query.count(),
        "active_members": User.query.filter_by(status="active").count(),
        "pending_payments": Payment.query.filter_by(status="pending").count(),
        "verified_payments": Payment.query.filter_by(status="verified").count(),
    })


@api_bp.get("/reports/monthly.csv")
@require_roles("admin", "community_admin")
def reports_monthly_csv():
    return Response(
        ReportExporter().monthly_payments_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=monthly-payments.csv"},
    )


@api_bp.get("/reports/yearly")
@require_roles("admin", "community_admin")
def reports_yearly():
    return reports_monthly()


@api_bp.get("/reports/voter-roll")
@require_roles("admin", "community_admin")
def reports_voter_roll():
    users = User.query.filter_by(status="active").all()
    return jsonify([user_json(user) for user in users if age_on(user.dob) is not None and age_on(user.dob) >= 21])


@api_bp.get("/settings")
@require_roles("admin")
def settings_get():
    return jsonify({setting.key: setting.value for setting in Setting.query.all()})


@api_bp.put("/settings")
@require_roles("admin")
def settings_put():
    actor = current_user()
    for key, value in payload().items():
        setting = db.session.get(Setting, key) or Setting(key=key, value=str(value))
        setting.value = str(value)
        db.session.add(setting)
        audit(actor, "settings.update", "setting", key)
    db.session.commit()
    return settings_get()


@api_bp.post("/payments/<provider>/webhook")
def payments_provider_webhook(provider: str):
    validate_choice(provider, "provider", PAYMENT_METHODS - {"manual"})
    PaymentProviderClient(provider).verify_webhook(request.headers.get("X-Payment-Signature"))
    return jsonify({"status": "accepted"})


@api_bp.post("/uploads/payment-proof-url")
@require_roles("admin", "community_admin", "community_user")
def payment_proof_upload_url():
    data = payload()
    require_fields(data, "blob_name")
    return jsonify({"upload_url": BlobStorageClient().signed_upload_url(data["blob_name"])})


@api_bp.get("/compliance/users/<int:member_id>/export")
@require_roles("admin")
def compliance_user_export(member_id: int):
    return Response(export_user_data_json(db.get_or_404(User, member_id)), mimetype="application/json")


@api_bp.post("/compliance/users/<int:member_id>/anonymize")
@require_roles("admin")
def compliance_user_anonymize(member_id: int):
    actor = current_user()
    user = db.get_or_404(User, member_id)
    if user.id == actor.id:
        return error("admins cannot anonymize their own active account", 400)
    anonymize_user(user, actor)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/compliance/audit/purge")
@require_roles("admin")
def compliance_audit_purge():
    actor = current_user()
    days = int(payload().get("retention_days", current_app.config["AUDIT_RETENTION_DAYS"]))
    count = purge_old_audit_logs(days, actor)
    db.session.commit()
    return jsonify({"purged": count})
