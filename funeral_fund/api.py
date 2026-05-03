from __future__ import annotations

from datetime import date
from decimal import Decimal

from flask import Blueprint, jsonify, request

from .auth import current_user, require_roles
from .extensions import db
from .models import FamilyMember, Fee, Notice, Payment, Setting, User, Vote, VoteCast, VoteOption
from .services import age_on, approve_member, audit, verify_payment

api_bp = Blueprint("api", __name__)


def payload() -> dict:
    return request.get_json(silent=True) or {}


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


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
@require_roles("admin", "leader")
def members_index():
    return jsonify([user_json(user) for user in User.query.order_by(User.created_at.desc()).all()])


@api_bp.post("/members")
@require_roles("admin", "leader")
def members_create():
    data = payload()
    actor = current_user()
    user = User(
        email=data["email"],
        name=data.get("name", data["email"]),
        role=data.get("role", "member"),
        status=data.get("status", "pending"),
        dob=parse_date(data.get("dob")),
    )
    db.session.add(user)
    db.session.flush()
    audit(actor, "member.create", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user)), 201


@api_bp.get("/members/<int:member_id>")
@require_roles("admin", "leader")
def members_show(member_id: int):
    return jsonify(user_json(db.get_or_404(User, member_id)))


@api_bp.put("/members/<int:member_id>")
@require_roles("admin", "leader")
def members_update(member_id: int):
    data = payload()
    actor = current_user()
    user = db.get_or_404(User, member_id)
    for field in ["name", "role", "status"]:
        if field in data:
            setattr(user, field, data[field])
    if "dob" in data:
        user.dob = parse_date(data["dob"])
    audit(actor, "member.update", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/approve")
@require_roles("admin", "leader")
def members_approve(member_id: int):
    actor = current_user()
    user = approve_member(db.get_or_404(User, member_id), actor)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/promote")
@require_roles("admin", "leader")
def members_promote(member_id: int):
    actor = current_user()
    user = db.get_or_404(User, member_id)
    user.role = "leader"
    audit(actor, "member.promote", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/suspend")
@require_roles("admin", "leader")
def members_suspend(member_id: int):
    actor = current_user()
    user = db.get_or_404(User, member_id)
    user.status = "suspended"
    audit(actor, "member.suspend", "user", user.id)
    db.session.commit()
    return jsonify(user_json(user))


@api_bp.post("/members/<int:member_id>/family")
@require_roles("admin", "leader", "member")
def family_create(member_id: int):
    actor = current_user()
    if actor.id != member_id and not actor.is_leadership:
        return jsonify({"error": "cannot modify another member family"}), 403
    data = payload()
    family = FamilyMember(
        user_id=member_id,
        name=data["name"],
        category=data["category"],
        relationship=data.get("relationship"),
        dob=parse_date(data.get("dob")),
    )
    db.session.add(family)
    db.session.flush()
    audit(actor, "family.create", "family_member", family.id)
    db.session.commit()
    return jsonify({"id": family.id, "name": family.name, "category": family.category}), 201


@api_bp.put("/family/<int:family_id>")
@require_roles("admin", "leader", "member")
def family_update(family_id: int):
    actor = current_user()
    family = db.get_or_404(FamilyMember, family_id)
    if actor.id != family.user_id and not actor.is_leadership:
        return jsonify({"error": "cannot modify another member family"}), 403
    data = payload()
    for field in ["name", "category", "relationship", "status"]:
        if field in data:
            setattr(family, field, data[field])
    if "dob" in data:
        family.dob = parse_date(data["dob"])
    audit(actor, "family.update", "family_member", family.id)
    db.session.commit()
    return jsonify({"id": family.id, "name": family.name, "category": family.category})


@api_bp.delete("/family/<int:family_id>")
@require_roles("admin", "leader", "member")
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
@require_roles("admin", "leader")
def fees_recurring_create():
    data = payload()
    fee = Fee(
        name=data["name"],
        type="recurring",
        amount=Decimal(str(data["amount"])),
        recurring_interval=data.get("recurring_interval", "monthly"),
    )
    db.session.add(fee)
    audit(current_user(), "fee.create", "fee", "pending", type="recurring")
    db.session.commit()
    return jsonify({"id": fee.id, "name": fee.name}), 201


@api_bp.post("/fees/one-time")
@require_roles("admin", "leader")
def fees_one_time_create():
    data = payload()
    fee = Fee(name=data["name"], type="one_time", amount=Decimal(str(data["amount"])))
    db.session.add(fee)
    audit(current_user(), "fee.create", "fee", "pending", type="one_time")
    db.session.commit()
    return jsonify({"id": fee.id, "name": fee.name}), 201


@api_bp.get("/notices/<notice_number>")
@require_roles("admin", "leader", "member")
def notices_show(notice_number: str):
    notice = Notice.query.filter_by(notice_number=notice_number).first_or_404()
    return jsonify({"notice_number": notice.notice_number, "title": notice.title, "amount": str(notice.amount)})


@api_bp.post("/payments/initiate")
@require_roles("admin", "leader", "member")
def payments_initiate():
    data = payload()
    actor = current_user()
    member_id = int(data.get("member_id", actor.id))
    if actor.id != member_id and not actor.is_leadership:
        return jsonify({"error": "cannot initiate payment for another member"}), 403
    payment = Payment(
        member_id=member_id,
        fee_id=data.get("fee_id"),
        notice_id=data.get("notice_id"),
        method=data.get("method", "manual"),
        amount=Decimal(str(data["amount"])),
    )
    db.session.add(payment)
    db.session.flush()
    audit(actor, "payment.initiate", "payment", payment.id)
    db.session.commit()
    return jsonify({"id": payment.id, "status": payment.status}), 201


@api_bp.post("/payments/proof")
@require_roles("admin", "leader", "member")
def payments_proof():
    data = payload()
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
@require_roles("admin", "leader")
def payments_verify():
    data = payload()
    payment = verify_payment(db.get_or_404(Payment, data["payment_id"]), current_user(), data["status"])
    db.session.commit()
    return jsonify({"id": payment.id, "status": payment.status})


@api_bp.post("/votes")
@require_roles("admin", "leader")
def votes_create():
    data = payload()
    vote = Vote(
        title=data["title"],
        description=data.get("description"),
        open_date=parse_date(data["open_date"]) or date.today(),
        close_date=parse_date(data["close_date"]) or date.today(),
    )
    for option in data.get("options", []):
        vote.options.append(VoteOption(label=option))
    db.session.add(vote)
    db.session.flush()
    audit(current_user(), "vote.create", "vote", vote.id)
    db.session.commit()
    return jsonify({"id": vote.id, "title": vote.title}), 201


@api_bp.post("/votes/<int:vote_id>/cast")
@require_roles("admin", "leader", "member")
def votes_cast(vote_id: int):
    actor = current_user()
    data = payload()
    vote = db.get_or_404(Vote, vote_id)
    today = date.today()
    if not (vote.open_date <= today <= vote.close_date):
        return jsonify({"error": "vote is closed"}), 400
    if actor.status != "active" or (age_on(actor.dob) is not None and age_on(actor.dob) < 21):
        return jsonify({"error": "member is not eligible to vote"}), 403
    cast = VoteCast(vote_id=vote.id, option_id=data["option_id"], member_id=actor.id)
    db.session.add(cast)
    audit(actor, "vote.cast", "vote", vote.id)
    db.session.commit()
    return jsonify({"id": cast.id}), 201


@api_bp.get("/votes/<int:vote_id>/results")
@require_roles("admin", "leader")
def votes_results(vote_id: int):
    vote = db.get_or_404(Vote, vote_id)
    results = []
    for option in vote.options:
        total = VoteCast.query.filter_by(vote_id=vote.id, option_id=option.id).count()
        results.append({"option_id": option.id, "label": option.label, "total": total})
    return jsonify({"vote_id": vote.id, "results": results})


@api_bp.get("/reports/monthly")
@require_roles("admin", "leader")
def reports_monthly():
    return jsonify({
        "members": User.query.count(),
        "active_members": User.query.filter_by(status="active").count(),
        "pending_payments": Payment.query.filter_by(status="pending").count(),
        "verified_payments": Payment.query.filter_by(status="verified").count(),
    })


@api_bp.get("/reports/yearly")
@require_roles("admin", "leader")
def reports_yearly():
    return reports_monthly()


@api_bp.get("/reports/voter-roll")
@require_roles("admin", "leader")
def reports_voter_roll():
    users = User.query.filter_by(status="active").all()
    return jsonify([user_json(user) for user in users if age_on(user.dob) is None or age_on(user.dob) >= 21])


@api_bp.get("/settings")
@require_roles("admin", "leader")
def settings_get():
    return jsonify({setting.key: setting.value for setting in Setting.query.all()})


@api_bp.put("/settings")
@require_roles("admin", "leader")
def settings_put():
    actor = current_user()
    for key, value in payload().items():
        setting = db.session.get(Setting, key) or Setting(key=key, value=str(value))
        setting.value = str(value)
        db.session.add(setting)
        audit(actor, "settings.update", "setting", key)
    db.session.commit()
    return settings_get()
