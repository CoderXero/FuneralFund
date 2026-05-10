from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, send_from_directory, session, url_for
import qrcode
import qrcode.image.svg
from sqlalchemy import func, or_
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .auth import current_user, login_required, require_roles
from .compliance import anonymize_user, export_user_data_json, purge_old_audit_logs
from .extensions import db
from .integrations import ReportExporter
from .models import AuditLog, FamilyMember, Fee, Message, Notice, Payment, Setting, User, Vote, VoteCast, VoteOption, utcnow
from .services import (
    FAMILY_CATEGORIES,
    FEE_TYPES,
    MESSAGE_AUDIENCES,
    PAYMENT_METHODS,
    RECURRING_INTERVALS,
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

web_bp = Blueprint("web", __name__)

PAYMENT_PROVIDERS = {
    "cashapp": "Cash App",
    "venmo": "Venmo",
    "zelle": "Zelle",
}

PAYMENT_OPTION_FIELDS = [
    "enabled",
    "display_name",
    "handle",
    "payment_url",
]
PAYMENT_PROOF_UPLOAD_DIR = "payment_proofs"
PAYMENT_PROOF_EXTENSIONS = {"gif", "jpeg", "jpg", "pdf", "png", "webp"}
PAYMENT_STATUSES = {"pending", "verified", "rejected"}
PAYMENT_DATE_RANGES = {"all", "week", "month", "year"}


@web_bp.get("/favicon.ico")
def favicon():
    return Response(status=204)


def parse_form_date(value: str | None, field: str = "date") -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def parse_form_decimal(value: str | None) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Amount must be a decimal number") from exc
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return amount


def flash_form_error(exc: Exception, endpoint: str):
    flash(str(exc), "danger")
    return redirect(url_for(endpoint))


def parse_optional_int(value: str | None, field: str) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer") from exc


def save_payment_proof_file(payment: Payment, upload: FileStorage | None) -> str | None:
    if upload is None or not upload.filename:
        return None
    original_name = secure_filename(upload.filename)
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if extension not in PAYMENT_PROOF_EXTENSIONS:
        raise ValueError("Proof file must be a PDF or image")
    upload_dir = Path(current_app.instance_path) / "uploads" / PAYMENT_PROOF_UPLOAD_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"payment-{payment.id}.{extension}"
    upload.save(upload_dir / filename)
    return url_for("web.payment_proof_file", filename=filename)


def payment_history_filters(include_member: bool = False) -> dict[str, str]:
    filters = {
        "status": request.args.get("status", ""),
        "fee_id": request.args.get("fee_id", ""),
        "date_range": request.args.get("date_range", "all"),
    }
    if filters["status"] not in PAYMENT_STATUSES:
        filters["status"] = ""
    if filters["date_range"] not in PAYMENT_DATE_RANGES:
        filters["date_range"] = "all"
    if include_member:
        filters["member_id"] = request.args.get("member_id", "")
    return filters


def apply_payment_history_filters(query, filters: dict[str, str]):
    if filters.get("status"):
        query = query.filter(Payment.status == filters["status"])
    if filters.get("fee_id"):
        try:
            query = query.filter(Payment.fee_id == int(filters["fee_id"]))
        except ValueError:
            query = query.filter(Payment.fee_id == -1)
    if filters.get("member_id"):
        try:
            query = query.filter(Payment.member_id == int(filters["member_id"]))
        except ValueError:
            query = query.filter(Payment.member_id == -1)
    date_range = filters.get("date_range", "all")
    days = {"week": 7, "month": 30, "year": 365}.get(date_range)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(Payment.created_at >= cutoff)
    return query


def fiscal_year_end(today: date | None = None) -> date:
    today = today or date.today()
    month = current_app.config["FISCAL_YEAR_END_MONTH"]
    day = current_app.config["FISCAL_YEAR_END_DAY"]
    end = date(today.year, month, day)
    if today > end:
        end = date(today.year + 1, month, day)
    return end


def settings_dict() -> dict[str, str]:
    return {setting.key: setting.value for setting in Setting.query.all()}


def setting_value(settings: dict[str, str], provider: str, field: str) -> str:
    return settings.get(f"payment_{provider}_{field}", "")


def payment_qr_value(settings: dict[str, str], provider: str) -> str | None:
    payment_url = setting_value(settings, provider, "payment_url").strip()
    handle = setting_value(settings, provider, "handle").strip()
    if payment_url:
        return payment_url
    if not handle:
        return None
    if provider == "cashapp":
        normalized = handle if handle.startswith("$") else f"${handle}"
        return f"https://cash.app/{quote(normalized)}"
    if provider == "venmo":
        return f"https://venmo.com/u/{quote(handle.lstrip('@'))}"
    if provider == "zelle":
        return f"ZELLE:{handle}"
    return handle


def active_payment_options(settings: dict[str, str]) -> list[dict[str, str]]:
    options = []
    for provider, label in PAYMENT_PROVIDERS.items():
        if setting_value(settings, provider, "enabled") != "1":
            continue
        if not payment_qr_value(settings, provider):
            continue
        options.append(
            {
                "provider": provider,
                "label": setting_value(settings, provider, "display_name") or label,
                "handle": setting_value(settings, provider, "handle"),
                "payment_url": setting_value(settings, provider, "payment_url"),
            }
        )
    return options


def user_setting_key(user: User, key: str) -> str:
    return f"user_{user.id}_{key}"


def user_settings(user: User) -> dict[str, str]:
    prefix = f"user_{user.id}_"
    return {
        setting.key.removeprefix(prefix): setting.value
        for setting in Setting.query.filter(Setting.key.startswith(prefix)).all()
    }


def set_user_setting(user: User, key: str, value: str) -> None:
    setting_key = user_setting_key(user, key)
    setting = db.session.get(Setting, setting_key) or Setting(key=setting_key, value="")
    setting.value = value
    db.session.add(setting)


def visible_messages(user: User, include_archived: bool = False) -> list[Message]:
    audiences = ["all"]
    if user.role == "community_user":
        audiences.append("community_user")
    query = Message.query
    if not include_archived:
        query = query.filter(Message.archived_at.is_(None))
    if user.is_leadership:
        audiences.extend(["community_user", "community_admin", "leadership"])
        return (
            query.filter(
                or_(
                    Message.recipient_id == user.id,
                    Message.sender_id == user.id,
                    Message.audience.in_(audiences),
                )
            )
            .order_by(Message.created_at.desc())
            .all()
        )
    return (
        query.filter(or_(Message.recipient_id == user.id, Message.audience.in_(audiences)))
        .order_by(Message.created_at.desc())
        .all()
    )


def landing_user() -> User | None:
    if session.get("user_id"):
        return db.session.get(User, session["user_id"])
    if request.headers.get("X-User-Email"):
        return current_user()
    return None


@web_bp.get("/")
def landing_page():
    return render_template(
        "landing.html",
        user=landing_user(),
        latest_notice=Notice.query.order_by(Notice.created_at.desc()).first(),
    )


@web_bp.get("/dashboard")
def dashboard():
    user = current_user()
    if user.is_leadership:
        member_count = User.query.count()
        pending_count = User.query.filter_by(status="pending").count()
        payments = Payment.query
        vote_count = Vote.query.count()
    else:
        member_count = 1
        pending_count = 1 if user.status == "pending" else 0
        payments = Payment.query.filter_by(member_id=user.id)
        vote_count = 0
    return render_template(
        "dashboard.html",
        user=user,
        member_count=member_count,
        pending_count=pending_count,
        payment_count=payments.count(),
        vote_count=vote_count,
    )


@web_bp.get("/my/family")
@login_required
def member_family_redirect():
    return redirect(url_for("web.member_page"))


@web_bp.get("/my/member")
@login_required
def member_page():
    user = current_user()
    return render_template(
        "member/member.html",
        user=user,
        family_members=FamilyMember.query.filter_by(user_id=user.id).order_by(FamilyMember.created_at.desc()).all(),
    )


@web_bp.post("/my/family")
@login_required
def member_family_create_page():
    user = current_user()
    try:
        category = request.form.get("category", "dependant")
        validate_choice(category, "category", FAMILY_CATEGORIES)
        family = FamilyMember(
            user_id=user.id,
            name=request.form["name"],
            category=category,
            relationship=request.form.get("relationship") or None,
            email=normalize_email(request.form["email"]) if request.form.get("email") else None,
            dob=parse_form_date(request.form.get("dob"), "dob"),
        )
    except ValueError as exc:
        return flash_form_error(exc, "web.member_page")
    db.session.add(family)
    db.session.flush()
    audit(user, "family.create", "family_member", family.id, source="web")
    db.session.commit()
    flash("Family member added.", "success")
    return redirect(url_for("web.member_page"))


@web_bp.post("/my/family/<int:family_id>/delete")
@login_required
def member_family_delete_page(family_id: int):
    user = current_user()
    family = db.get_or_404(FamilyMember, family_id)
    if family.user_id != user.id and not user.is_leadership:
        return Response(status=403)
    audit(user, "family.delete", "family_member", family.id, source="web")
    db.session.delete(family)
    db.session.commit()
    flash("Family member removed.", "success")
    return redirect(url_for("web.member_page"))


@web_bp.get("/my/settings")
@login_required
def member_settings_page():
    user = current_user()
    return render_template(
        "member/settings.html",
        user=user,
        member_settings=user_settings(user),
        payment_providers=PAYMENT_PROVIDERS,
    )


@web_bp.post("/my/settings")
@login_required
def member_settings_update_page():
    user = current_user()
    try:
        preferred_provider = request.form.get("preferred_payment_provider", "")
        validate_choice(preferred_provider, "preferred_payment_provider", set(PAYMENT_PROVIDERS) | {""})
        user.name = request.form.get("name") or user.name
        user.dob = parse_form_date(request.form.get("dob"), "dob")
    except ValueError as exc:
        return flash_form_error(exc, "web.member_settings_page")
    for key in [
        "whatsapp_number",
        "preferred_payment_provider",
        "cashapp_handle",
        "venmo_handle",
        "zelle_handle",
    ]:
        set_user_setting(user, key, request.form.get(key, ""))
    audit(user, "member.settings.update", "user", user.id, source="web")
    db.session.commit()
    flash("Profile settings saved.", "success")
    return redirect(url_for("web.member_settings_page"))


@web_bp.get("/my/messages")
@login_required
def member_messages_page():
    user = current_user()
    return render_template("member/messages.html", user=user, messages=visible_messages(user))


@web_bp.post("/my/messages")
@login_required
def member_message_send_page():
    user = current_user()
    message = Message(
        sender_id=user.id,
        audience="leadership",
        subject=request.form["subject"],
        body=request.form["body"],
    )
    db.session.add(message)
    db.session.flush()
    audit(user, "message.send", "message", message.id, source="web", audience="leadership")
    db.session.commit()
    flash("Message sent to leadership.", "success")
    return redirect(url_for("web.member_messages_page"))


@web_bp.get("/my/payments")
@login_required
def member_payments_page():
    user = current_user()
    settings = settings_dict()
    filters = payment_history_filters()
    fee_options = (
        Fee.query.join(Payment, Payment.fee_id == Fee.id)
        .filter(Payment.member_id == user.id)
        .order_by(Fee.name.asc())
        .distinct()
        .all()
    )
    payments = apply_payment_history_filters(
        Payment.query.filter_by(member_id=user.id),
        filters,
    ).order_by(Payment.created_at.desc())
    return render_template(
        "member/payments.html",
        user=user,
        payments=payments.all(),
        fees=Fee.query.filter_by(active=True).order_by(Fee.created_at.desc()).all(),
        payment_options=active_payment_options(settings),
        payment_filters=filters,
        payment_statuses=sorted(PAYMENT_STATUSES),
        fee_options=fee_options,
    )


@web_bp.post("/my/payments")
@login_required
def member_payment_create_page():
    user = current_user()
    try:
        fee_id = parse_optional_int(request.form.get("fee_id"), "fee_id")
        method = request.form.get("method", "manual")
        validate_choice(method, "method", PAYMENT_METHODS)
        amount = parse_form_decimal(request.form.get("amount"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("web.member_payments_page"))
    payment = Payment(
        member_id=user.id,
        fee_id=fee_id,
        method=method,
        amount=amount,
    )
    db.session.add(payment)
    db.session.flush()
    audit(user, "payment.initiate", "payment", payment.id, source="web")
    db.session.commit()
    flash("Payment started. Add proof after sending payment.", "success")
    return redirect(url_for("web.member_payments_page"))


@web_bp.post("/my/payments/<int:payment_id>/proof")
@login_required
def member_payment_proof_page(payment_id: int):
    user = current_user()
    payment = db.get_or_404(Payment, payment_id)
    if payment.member_id != user.id and not user.is_leadership:
        return Response(status=403)
    try:
        uploaded_proof_url = save_payment_proof_file(payment, request.files.get("proof_file"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("web.member_payments_page"))
    payment.proof_url = uploaded_proof_url or request.form.get("proof_url") or payment.proof_url
    payment.transaction_id = request.form.get("transaction_id") or None
    payment.notes = request.form.get("notes") or None
    audit(user, "payment.proof", "payment", payment.id, source="web")
    db.session.commit()
    flash("Payment proof saved.", "success")
    return redirect(url_for("web.member_payments_page"))


@web_bp.get("/payments/proofs/<path:filename>")
@login_required
def payment_proof_file(filename: str):
    user = current_user()
    expected_url = url_for("web.payment_proof_file", filename=filename)
    payment = Payment.query.filter_by(proof_url=expected_url).one_or_none()
    if payment is None:
        return Response(status=404)
    if payment.member_id != user.id and not user.is_leadership:
        return Response(status=403)
    upload_dir = Path(current_app.instance_path) / "uploads" / PAYMENT_PROOF_UPLOAD_DIR
    return send_from_directory(upload_dir, filename)


@web_bp.get("/my/voting")
@login_required
def member_voting_page():
    user = current_user()
    today = date.today()
    votes = Vote.query.filter(Vote.open_date <= today, Vote.close_date >= today).order_by(Vote.close_date.asc()).all()
    casts = {cast.vote_id: cast for cast in VoteCast.query.filter_by(member_id=user.id).all()}
    user_age = age_on(user.dob)
    eligible = user.status == "active" and user_age is not None and user_age >= 21
    return render_template("member/voting.html", user=user, votes=votes, casts=casts, eligible=eligible)


@web_bp.post("/my/voting/<int:vote_id>/cast")
@login_required
def member_vote_cast_page(vote_id: int):
    user = current_user()
    vote = db.get_or_404(Vote, vote_id)
    today = date.today()
    user_age = age_on(user.dob)
    if not (vote.open_date <= today <= vote.close_date):
        flash("This vote is closed.", "danger")
        return redirect(url_for("web.member_voting_page"))
    if user.status != "active" or user_age is None or user_age < 21:
        flash("You are not eligible to vote.", "danger")
        return redirect(url_for("web.member_voting_page"))
    if VoteCast.query.filter_by(vote_id=vote.id, member_id=user.id).one_or_none():
        flash("Your vote has already been recorded.", "warning")
        return redirect(url_for("web.member_voting_page"))
    option = VoteOption.query.filter_by(id=request.form["option_id"], vote_id=vote.id).one_or_none()
    if option is None:
        flash("Choose a valid option.", "danger")
        return redirect(url_for("web.member_voting_page"))
    cast = VoteCast(vote_id=vote.id, option_id=option.id, member_id=user.id)
    db.session.add(cast)
    audit(user, "vote.cast", "vote", vote.id, source="web")
    db.session.commit()
    flash("Vote recorded.", "success")
    return redirect(url_for("web.member_voting_page"))


@web_bp.get("/admin")
@require_roles("admin", "community_admin")
def admin_page():
    return render_template(
        "admin/index.html",
        user=current_user(),
        member_count=User.query.count(),
        pending_payments=Payment.query.filter_by(status="pending").count(),
        open_votes=Vote.query.filter(Vote.open_date <= date.today(), Vote.close_date >= date.today()).count(),
        leadership_messages=Message.query.filter_by(audience="leadership", archived_at=None).count(),
    )


@web_bp.get("/admin/compliance")
@require_roles("admin")
def admin_compliance_page():
    return render_template(
        "admin/compliance.html",
        user=current_user(),
        members=User.query.order_by(User.created_at.desc()).all(),
        audit_logs=AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all(),
        audit_retention_days=current_app.config["AUDIT_RETENTION_DAYS"],
    )


@web_bp.get("/admin/reports/members.csv")
@require_roles("admin", "community_admin")
def admin_members_csv():
    return Response(
        ReportExporter().members_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=members.csv"},
    )


@web_bp.get("/admin/reports/payments.csv")
@require_roles("admin", "community_admin")
def admin_payments_csv():
    return Response(
        ReportExporter().monthly_payments_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=payments.csv"},
    )


@web_bp.get("/admin/reports/audit.csv")
@require_roles("admin")
def admin_audit_csv():
    return Response(
        ReportExporter().audit_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit.csv"},
    )


@web_bp.get("/admin/compliance/users/<int:member_id>/export")
@require_roles("admin")
def admin_user_export(member_id: int):
    return Response(
        export_user_data_json(db.get_or_404(User, member_id)),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=user-{member_id}-export.json"},
    )


@web_bp.post("/admin/compliance/users/<int:member_id>/anonymize")
@require_roles("admin")
def admin_user_anonymize(member_id: int):
    actor = current_user()
    member = db.get_or_404(User, member_id)
    if member.id == actor.id:
        flash("Admins cannot anonymize their own active account.", "danger")
        return redirect(url_for("web.admin_compliance_page"))
    anonymize_user(member, actor)
    db.session.commit()
    flash("User anonymized.", "warning")
    return redirect(url_for("web.admin_compliance_page"))


@web_bp.post("/admin/compliance/audit/purge")
@require_roles("admin")
def admin_audit_purge():
    count = purge_old_audit_logs(current_app.config["AUDIT_RETENTION_DAYS"], current_user())
    db.session.commit()
    flash(f"Purged {count} old audit log entries.", "success")
    return redirect(url_for("web.admin_compliance_page"))


@web_bp.get("/admin/messages")
@require_roles("admin", "community_admin")
def admin_messages_page():
    user = current_user()
    return render_template(
        "admin/messages.html",
        user=user,
        messages=visible_messages(user, include_archived=True),
    )


@web_bp.post("/admin/messages")
@require_roles("admin", "community_admin")
def admin_message_send_page():
    user = current_user()
    try:
        delivery = request.form.get("delivery", "broadcast")
        validate_choice(delivery, "delivery", {"broadcast", "direct"})
        recipient = None
        if delivery == "direct":
            recipient_email = request.form.get("recipient_email", "").strip().lower()
            if not recipient_email:
                raise ValueError("recipient_email is required for direct messages")
            recipient = User.query.filter(func.lower(User.email) == recipient_email).one_or_none()
            if recipient is None:
                raise ValueError("recipient_email must match an existing member")
        audience = request.form.get("audience", "all") if recipient is None else "direct"
        if audience != "direct":
            validate_choice(audience, "audience", MESSAGE_AUDIENCES)
        message = Message(
            sender_id=user.id,
            recipient_id=recipient.id if recipient else None,
            audience=audience,
            subject=request.form["subject"],
            body=request.form["body"],
        )
    except ValueError as exc:
        return flash_form_error(exc, "web.admin_messages_page")
    db.session.add(message)
    db.session.flush()
    audit(user, "message.send", "message", message.id, source="web", audience=message.audience)
    db.session.commit()
    flash("Message sent.", "success")
    return redirect(url_for("web.admin_messages_page"))


@web_bp.post("/admin/messages/<int:message_id>/archive")
@require_roles("admin", "community_admin")
def admin_message_archive_page(message_id: int):
    user = current_user()
    message = db.get_or_404(Message, message_id)
    if message.archived_at is None:
        message.archived_at = utcnow()
        message.retain_until = fiscal_year_end(message.archived_at.date())
        audit(user, "message.archive", "message", message.id, source="web", retain_until=message.retain_until.isoformat())
        db.session.commit()
        flash("Message archived.", "success")
    return redirect(url_for("web.admin_messages_page"))


@web_bp.get("/members")
@require_roles("admin", "community_admin")
def members_page():
    return render_template(
        "members/index.html",
        user=current_user(),
        members=User.query.order_by(User.created_at.desc()).all(),
    )


@web_bp.post("/members")
@require_roles("admin", "community_admin")
def members_create_page():
    actor = current_user()
    try:
        role = request.form.get("role", "community_user")
        status = request.form.get("status", "pending")
        ensure_role_assignment_allowed(actor, role)
        validate_choice(status, "status", STATUSES)
        member = User(
            email=normalize_email(request.form["email"]),
            name=request.form.get("name") or request.form["email"],
            role=role,
            status=status,
            dob=parse_form_date(request.form.get("dob"), "dob"),
        )
    except (PermissionError, ValueError) as exc:
        return flash_form_error(exc, "web.members_page")
    db.session.add(member)
    db.session.flush()
    audit(actor, "member.create", "user", member.id, source="web")
    db.session.commit()
    flash("Member created.", "success")
    return redirect(url_for("web.members_page"))


@web_bp.post("/members/<int:member_id>/approve")
@require_roles("admin", "community_admin")
def members_approve_page(member_id: int):
    approve_member(db.get_or_404(User, member_id), current_user())
    db.session.commit()
    flash("Member approved.", "success")
    return redirect(url_for("web.members_page"))


@web_bp.post("/members/<int:member_id>/promote")
@require_roles("admin", "community_admin")
def members_promote_page(member_id: int):
    actor = current_user()
    member = db.get_or_404(User, member_id)
    try:
        promote_member(member, actor, source="web")
    except (PermissionError, ValueError) as exc:
        return flash_form_error(exc, "web.members_page")
    db.session.commit()
    flash("Member promoted to leadership.", "success")
    return redirect(url_for("web.members_page"))


@web_bp.post("/members/<int:member_id>/suspend")
@require_roles("admin", "community_admin")
def members_suspend_page(member_id: int):
    actor = current_user()
    member = db.get_or_404(User, member_id)
    member.status = "suspended"
    audit(actor, "member.suspend", "user", member.id, source="web")
    db.session.commit()
    flash("Member suspended.", "warning")
    return redirect(url_for("web.members_page"))


@web_bp.get("/payments")
@require_roles("admin", "community_admin")
def payments_page():
    filters = payment_history_filters(include_member=True)
    payments = apply_payment_history_filters(Payment.query, filters).order_by(Payment.created_at.desc())
    fee_options = Fee.query.join(Payment, Payment.fee_id == Fee.id).order_by(Fee.name.asc()).distinct().all()
    return render_template(
        "payments/index.html",
        user=current_user(),
        payments=payments.all(),
        fees=Fee.query.order_by(Fee.created_at.desc()).all(),
        members=User.query.order_by(User.name.asc()).all(),
        payment_filters=filters,
        payment_statuses=sorted(PAYMENT_STATUSES),
        fee_options=fee_options,
    )


@web_bp.post("/fees")
@require_roles("admin", "community_admin")
def fees_create_page():
    actor = current_user()
    try:
        fee_type = request.form.get("type", "one_time")
        recurring_interval = request.form.get("recurring_interval") or ""
        validate_choice(fee_type, "type", FEE_TYPES)
        validate_choice(recurring_interval, "recurring_interval", RECURRING_INTERVALS)
        fee = Fee(
            name=request.form["name"],
            type=fee_type,
            amount=parse_form_decimal(request.form.get("amount")),
            recurring_interval=recurring_interval or None,
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("web.payments_page"))
    db.session.add(fee)
    db.session.flush()
    audit(actor, "fee.create", "fee", fee.id, source="web", type=fee.type)
    db.session.commit()
    flash("Fee created.", "success")
    return redirect(url_for("web.payments_page"))


@web_bp.post("/payments/<int:payment_id>/verify")
@require_roles("admin", "community_admin")
def payments_verify_page(payment_id: int):
    verify_payment(db.get_or_404(Payment, payment_id), current_user(), "verified")
    db.session.commit()
    flash("Payment verified.", "success")
    return redirect(url_for("web.payments_page"))


@web_bp.post("/payments/<int:payment_id>/reject")
@require_roles("admin", "community_admin")
def payments_reject_page(payment_id: int):
    verify_payment(db.get_or_404(Payment, payment_id), current_user(), "rejected")
    db.session.commit()
    flash("Payment rejected.", "warning")
    return redirect(url_for("web.payments_page"))


@web_bp.get("/voting")
@require_roles("admin", "community_admin")
def voting_page():
    votes = Vote.query.order_by(Vote.created_at.desc()).all()
    vote_results = {
        option.id: VoteCast.query.filter_by(vote_id=vote.id, option_id=option.id).count()
        for vote in votes
        for option in vote.options
    }
    return render_template(
        "voting/index.html",
        user=current_user(),
        votes=votes,
        vote_results=vote_results,
    )


@web_bp.post("/voting")
@require_roles("admin", "community_admin")
def voting_create_page():
    actor = current_user()
    labels = [
        label.strip()
        for label in [
            request.form.get("option_1", ""),
            request.form.get("option_2", ""),
            request.form.get("option_3", ""),
            request.form.get("option_4", ""),
        ]
        if label.strip()
    ]
    if len(labels) < 2:
        flash("A vote requires at least two options.", "danger")
        return redirect(url_for("web.voting_page"))
    try:
        open_date = parse_form_date(request.form.get("open_date"), "open_date") or date.today()
        close_date = parse_form_date(request.form.get("close_date"), "close_date") or date.today()
        if close_date < open_date:
            raise ValueError("close_date must be on or after open_date")
        vote = Vote(
            title=request.form["title"],
            description=request.form.get("description") or None,
            open_date=open_date,
            close_date=close_date,
        )
    except ValueError as exc:
        return flash_form_error(exc, "web.voting_page")
    for label in labels:
        vote.options.append(VoteOption(label=label))
    db.session.add(vote)
    db.session.flush()
    audit(actor, "vote.create", "vote", vote.id, source="web")
    db.session.commit()
    flash("Vote created.", "success")
    return redirect(url_for("web.voting_page"))


@web_bp.get("/settings")
@require_roles("admin")
def settings_page():
    settings = settings_dict()
    return render_template(
        "settings/index.html",
        user=current_user(),
        settings=settings,
        payment_providers=PAYMENT_PROVIDERS,
    )


@web_bp.post("/settings")
@require_roles("admin")
def settings_update_page():
    actor = current_user()
    keys = ["brand_name", "contact_email", "payment_instructions", "whatsapp_number"]
    for provider in PAYMENT_PROVIDERS:
        for field in PAYMENT_OPTION_FIELDS:
            keys.append(f"payment_{provider}_{field}")
    for key in keys:
        setting = db.session.get(Setting, key) or Setting(key=key, value="")
        if key.endswith("_enabled"):
            setting.value = "1" if request.form.get(key) == "1" else "0"
        else:
            setting.value = request.form.get(key, "")
        db.session.add(setting)
        audit(actor, "settings.update", "setting", key, source="web")
    db.session.commit()
    flash("Settings saved.", "success")
    return redirect(url_for("web.settings_page"))


@web_bp.get("/settings/payment-options/<provider>/qr.svg")
@require_roles("admin", "community_admin", "community_user")
def payment_option_qr(provider: str):
    if provider not in PAYMENT_PROVIDERS:
        return Response(status=404)
    settings = settings_dict()
    qr_value = payment_qr_value(settings, provider)
    if not qr_value:
        return Response(status=404)

    image = qrcode.make(qr_value, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return Response(buffer.getvalue(), mimetype="image/svg+xml")
