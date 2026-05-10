from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from funeral_fund.extensions import db
from funeral_fund.models import FamilyMember, Fee, Message, Notice, Payment, Setting, User, Vote, VoteCast, VoteOption


def test_landing_page_is_public_without_nav(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"FuneralFund" in response.data
    assert b'href="/dashboard"' not in response.data
    assert b'href="/members"' not in response.data
    assert b"Sign in" in response.data


def test_landing_page_shows_latest_notice(client, app):
    with app.app_context():
        db.session.add(Notice(notice_number="N-001", title="Older Notice", amount="10.00"))
        db.session.add(Notice(notice_number="N-002", title="Recent Notice", amount="25.00"))
        db.session.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Recent Notice" in response.data
    assert b"N-002" in response.data


def test_member_cannot_view_global_members_page(client, member_headers):
    response = client.get("/members", headers=member_headers)

    assert response.status_code == 403


def test_leader_can_view_global_members_page(client, leader_headers):
    response = client.get("/members", headers=leader_headers)

    assert response.status_code == 200


def test_dashboard_shows_sign_out_button(client, leader_headers):
    response = client.get("/dashboard", headers=leader_headers)

    assert response.status_code == 200
    assert b'action="/auth/logout"' in response.data
    assert b"Sign out" in response.data
    assert b"Leader | Leader" in response.data


def test_leadership_nav_includes_admin_tab(client, leader_headers):
    response = client.get("/dashboard", headers=leader_headers)

    assert b'href="/my/member"' in response.data
    assert b'href="/my/settings"' in response.data
    assert b'href="/my/messages"' in response.data
    assert b'href="/admin"' in response.data


def test_admin_pages_show_pinned_admin_operation_tabs(client, leader_headers):
    response = client.get("/admin", headers=leader_headers)

    assert response.status_code == 200
    assert b"position-sticky" in response.data
    assert b'href="/members">Manage members' in response.data
    assert b'href="/payments">Manage Payments' in response.data
    assert b'href="/voting">Manage voting' in response.data
    assert b'href="/admin/messages">Manage messages' in response.data
    assert b'href="/admin/reports/members.csv">Members CSV' in response.data
    assert b'href="/admin/reports/payments.csv">Payment CSV' in response.data


def test_member_nav_includes_self_service_pages(client, member_headers):
    response = client.get("/dashboard", headers=member_headers)

    assert response.status_code == 200
    assert b'href="/my/member"' in response.data
    assert b'href="/my/payments"' in response.data
    assert b'href="/my/voting"' in response.data
    assert b'href="/my/settings"' in response.data
    assert b'href="/my/messages"' in response.data
    assert b'href="/settings"' not in response.data
    assert b'href="/admin"' not in response.data


def test_leader_can_create_member_from_ui(client, leader_headers, app):
    response = client.post(
        "/members",
        data={
            "email": "ui-member@example.test",
            "name": "UI Member",
            "role": "community_user",
            "status": "pending",
        },
        headers=leader_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        member = User.query.filter_by(email="ui-member@example.test").one()
        assert member.name == "UI Member"


def test_leader_can_create_fee_from_ui(client, leader_headers, app):
    response = client.post(
        "/fees",
        data={"name": "Monthly Dues", "amount": "25.00", "type": "recurring", "recurring_interval": "monthly"},
        headers=leader_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        fee = Fee.query.filter_by(name="Monthly Dues").one()
        assert str(fee.amount) == "25.00"


def test_leader_can_create_vote_from_ui(client, leader_headers, app):
    response = client.post(
        "/voting",
        data={
            "title": "Budget",
            "open_date": "2026-01-01",
            "close_date": "2026-01-02",
            "option_1": "Yes",
            "option_2": "No",
        },
        headers=leader_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        vote = Vote.query.filter_by(title="Budget").one()
        assert len(vote.options) == 2


def test_admin_can_update_settings_from_ui(client, admin_headers, app):
    response = client.post(
        "/settings",
        data={
            "brand_name": "Community Fund",
            "contact_email": "contact@example.test",
            "whatsapp_number": "+15555550100",
            "payment_instructions": "Send proof after payment.",
            "payment_cashapp_enabled": "1",
            "payment_cashapp_display_name": "Cash App",
            "payment_cashapp_handle": "$communityfund",
            "payment_cashapp_payment_url": "https://cash.app/$communityfund",
            "payment_venmo_enabled": "1",
            "payment_venmo_display_name": "Venmo",
            "payment_venmo_handle": "communityfund",
            "payment_zelle_enabled": "1",
            "payment_zelle_display_name": "Zelle",
            "payment_zelle_handle": "payments@example.test",
        },
        headers=admin_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        assert db_value("brand_name") == "Community Fund"
        assert db_value("payment_instructions") == "Send proof after payment."
        assert db_value("payment_cashapp_enabled") == "1"
        assert db_value("payment_venmo_handle") == "communityfund"
        assert db_value("payment_zelle_handle") == "payments@example.test"


def test_settings_page_does_not_render_payment_secrets(client, admin_headers):
    response = client.get("/settings", headers=admin_headers)

    assert response.status_code == 200
    assert b"api_key" not in response.data
    assert b"webhook_secret" not in response.data


def test_leader_cannot_use_app_settings(client, leader_headers):
    response = client.get("/settings", headers=leader_headers)

    assert response.status_code == 403


def test_settings_page_shows_payment_option_qr(client, admin_headers, app):
    client.post(
        "/settings",
        data={
            "payment_cashapp_enabled": "1",
            "payment_cashapp_display_name": "Cash App",
            "payment_cashapp_handle": "$communityfund",
        },
        headers=admin_headers,
    )

    response = client.get("/settings", headers=admin_headers)

    assert response.status_code == 200
    assert b"/settings/payment-options/cashapp/qr.svg" in response.data


def test_payment_option_qr_returns_svg(client, admin_headers, leader_headers):
    client.post(
        "/settings",
        data={
            "payment_venmo_enabled": "1",
            "payment_venmo_display_name": "Venmo",
            "payment_venmo_handle": "communityfund",
        },
        headers=admin_headers,
    )

    response = client.get("/settings/payment-options/venmo/qr.svg", headers=leader_headers)

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert b"<svg" in response.data


def test_member_can_manage_family_from_ui(client, member_headers, app):
    page = client.get("/my/member", headers=member_headers)
    assert page.status_code == 200
    assert b"Family group" in page.data

    response = client.post(
        "/my/family",
        data={
            "name": "Child One",
            "relationship": "Child",
            "email": "Child.One@Example.Test",
            "category": "dependant",
            "dob": "2020-01-01",
        },
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        family = FamilyMember.query.filter_by(name="Child One").one()
        assert family.email == "child.one@example.test"
        family_id = family.id

    response = client.post(f"/my/family/{family_id}/delete", headers=member_headers)

    assert response.status_code == 302
    with app.app_context():
        assert FamilyMember.query.filter_by(id=family_id).one_or_none() is None


def test_my_family_redirects_to_my_member(client, member_headers):
    response = client.get("/my/family", headers=member_headers)

    assert response.status_code == 302
    assert response.headers["Location"] == "/my/member"


def test_member_can_update_my_settings(client, member_headers, app):
    client.get("/dashboard", headers=member_headers)

    response = client.post(
        "/my/settings",
        data={
            "name": "Updated Member",
            "dob": "1990-01-01",
            "whatsapp_number": "+15555550123",
            "preferred_payment_provider": "zelle",
            "cashapp_handle": "$member",
            "venmo_handle": "member",
            "zelle_handle": "member@example.test",
        },
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        assert member.name == "Updated Member"
        assert db_value(f"user_{member.id}_whatsapp_number") == "+15555550123"
        assert db_value(f"user_{member.id}_preferred_payment_provider") == "zelle"


def test_member_can_start_payment_and_save_proof_from_ui(client, member_headers, admin_headers, app):
    client.post(
        "/settings",
        data={
            "payment_cashapp_enabled": "1",
            "payment_cashapp_display_name": "Cash App",
            "payment_cashapp_handle": "$communityfund",
        },
        headers=admin_headers,
    )
    with app.app_context():
        fee = Fee(name="Monthly Dues", type="recurring", amount="25.00", recurring_interval="monthly")
        db.session.add(fee)
        db.session.commit()
        fee_id = fee.id

    page = client.get("/my/payments", headers=member_headers)
    assert b"/settings/payment-options/cashapp/qr.svg" in page.data

    response = client.post(
        "/my/payments",
        data={"fee_id": str(fee_id), "amount": "25.00", "method": "cashapp"},
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        payment = Payment.query.filter_by(method="cashapp").one()
        payment_id = payment.id

    response = client.post(
        f"/my/payments/{payment_id}/proof",
        data={"transaction_id": "TX123", "proof_url": "https://example.test/proof.png", "notes": "Paid"},
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.transaction_id == "TX123"
        assert payment.proof_url == "https://example.test/proof.png"


def test_member_can_filter_own_payment_history(client, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        monthly_fee = Fee(name="Monthly Dues", type="recurring", amount="25.00", recurring_interval="monthly")
        event_fee = Fee(name="Event Support", type="one_time", amount="20.00")
        db.session.add_all([monthly_fee, event_fee])
        db.session.flush()
        verified = Payment(member_id=member.id, fee_id=monthly_fee.id, method="manual", amount="10.00", status="verified")
        pending = Payment(member_id=member.id, fee_id=event_fee.id, method="manual", amount="20.00", status="pending")
        old = Payment(
            member_id=member.id,
            fee_id=monthly_fee.id,
            method="manual",
            amount="30.00",
            status="verified",
            created_at=datetime.now(timezone.utc) - timedelta(days=40),
        )
        db.session.add_all([verified, pending, old])
        db.session.commit()
        verified_id = verified.id
        pending_id = pending.id
        old_id = old.id
        event_fee_id = event_fee.id

    response = client.get("/my/payments?status=verified&date_range=month", headers=member_headers)

    assert response.status_code == 200
    assert b'<select class="form-select" id="history_fee_id" name="fee_id">' in response.data
    assert b"Monthly Dues" in response.data
    assert b"Event Support" in response.data
    assert f"<td>{verified_id}</td>".encode() in response.data
    assert f"<td>{pending_id}</td>".encode() not in response.data
    assert f"<td>{old_id}</td>".encode() not in response.data

    response = client.get(f"/my/payments?fee_id={event_fee_id}&date_range=all", headers=member_headers)

    assert f"<td>{pending_id}</td>".encode() in response.data
    assert f"<td>{verified_id}</td>".encode() not in response.data


def test_leader_can_filter_payment_history_by_member_status_and_date(client, leader_headers, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    client.get("/dashboard", headers=leader_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        leader = User.query.filter_by(email="leader@example.test").one()
        monthly_fee = Fee(name="Monthly Dues", type="recurring", amount="25.00", recurring_interval="monthly")
        support_fee = Fee(name="Support Notice", type="one_time", amount="40.00")
        db.session.add_all([monthly_fee, support_fee])
        db.session.flush()
        target = Payment(member_id=member.id, fee_id=support_fee.id, method="manual", amount="10.00", status="rejected")
        other_member = Payment(member_id=leader.id, fee_id=support_fee.id, method="manual", amount="20.00", status="rejected")
        wrong_status = Payment(member_id=member.id, fee_id=monthly_fee.id, method="manual", amount="30.00", status="pending")
        old = Payment(
            member_id=member.id,
            fee_id=support_fee.id,
            method="manual",
            amount="40.00",
            status="rejected",
            created_at=datetime.now(timezone.utc) - timedelta(days=400),
        )
        db.session.add_all([target, other_member, wrong_status, old])
        db.session.commit()
        member_id = member.id
        target_id = target.id
        other_member_id = other_member.id
        wrong_status_id = wrong_status.id
        old_id = old.id

    response = client.get(
        f"/payments?member_id={member_id}&status=rejected&date_range=year",
        headers=leader_headers,
    )

    assert response.status_code == 200
    assert b'<select class="form-select" id="history_fee_id" name="fee_id">' in response.data
    assert b"Support Notice" in response.data
    assert b"Monthly Dues" in response.data
    assert f"<td>{target_id}</td>".encode() in response.data
    assert f"<td>{other_member_id}</td>".encode() not in response.data
    assert f"<td>{wrong_status_id}</td>".encode() not in response.data
    assert f"<td>{old_id}</td>".encode() not in response.data


def test_member_can_upload_payment_proof_for_leadership_review(client, member_headers, leader_headers, app):
    client.get("/dashboard", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        payment = Payment(member_id=member.id, method="manual", amount="25.00")
        db.session.add(payment)
        db.session.commit()
        payment_id = payment.id

    response = client.post(
        f"/my/payments/{payment_id}/proof",
        data={
            "transaction_id": "TX-UPLOAD",
            "notes": "Receipt attached",
            "proof_file": (BytesIO(b"%PDF-1.4 proof"), "receipt.pdf"),
        },
        headers=member_headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        assert payment.proof_url == f"/payments/proofs/payment-{payment_id}.pdf"

    review = client.get("/payments", headers=leader_headers)
    assert b"Review proof" in review.data
    assert f"/payments/proofs/payment-{payment_id}.pdf".encode() in review.data

    proof = client.get(f"/payments/proofs/payment-{payment_id}.pdf", headers=leader_headers)
    assert proof.status_code == 200
    assert proof.data == b"%PDF-1.4 proof"


def test_other_member_cannot_view_payment_proof(client, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        payment = Payment(
            member_id=member.id,
            method="manual",
            amount="25.00",
            proof_url="/payments/proofs/payment-private.pdf",
        )
        db.session.add(payment)
        db.session.commit()

    response = client.get(
        "/payments/proofs/payment-private.pdf",
        headers={
            "X-User-Email": "other@example.test",
            "X-User-Name": "Other",
            "X-User-Groups": "community_member",
        },
    )

    assert response.status_code == 403


def test_member_can_cast_vote_from_ui(client, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        member.status = "active"
        member.dob = date(1990, 1, 1)
        vote = Vote(
            title="Board Election",
            open_date=date.today() - timedelta(days=1),
            close_date=date.today() + timedelta(days=1),
        )
        vote.options.append(VoteOption(label="A"))
        vote.options.append(VoteOption(label="B"))
        db.session.add(vote)
        db.session.commit()
        member_id = member.id
        vote_id = vote.id
        option_id = vote.options[0].id

    response = client.post(
        f"/my/voting/{vote_id}/cast",
        data={"option_id": str(option_id)},
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        assert VoteCast.query.filter_by(vote_id=vote_id, member_id=member_id).count() == 1


def test_member_can_send_message_to_leadership(client, member_headers, app):
    response = client.post(
        "/my/messages",
        data={"subject": "Need help", "body": "Please review my payment."},
        headers=member_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        message = Message.query.filter_by(subject="Need help").one()
        assert message.audience == "leadership"
        assert message.sender.email == "member@example.test"


def test_leader_can_send_admin_broadcast_message(client, leader_headers, member_headers, app):
    client.get("/dashboard", headers=member_headers)

    response = client.post(
        "/admin/messages",
        data={
            "delivery": "broadcast",
            "audience": "community_user",
            "subject": "Meeting",
            "body": "Monthly meeting tonight.",
        },
        headers=leader_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        message = Message.query.filter_by(subject="Meeting").one()
        assert message.audience == "community_user"

    inbox = client.get("/my/messages", headers=member_headers)
    assert b"Meeting" in inbox.data


def test_leader_can_send_direct_message_to_member(client, leader_headers, member_headers, app):
    client.get("/dashboard", headers=member_headers)

    response = client.post(
        "/admin/messages",
        data={
            "delivery": "direct",
            "recipient_email": "member@example.test",
            "subject": "Direct note",
            "body": "Please update your profile.",
        },
        headers=leader_headers,
    )

    assert response.status_code == 302
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        message = Message.query.filter_by(subject="Direct note").one()
        assert message.audience == "direct"
        assert message.recipient_id == member.id

    member_inbox = client.get("/my/messages", headers=member_headers)
    assert b"Direct note" in member_inbox.data

    leader_history = client.get("/admin/messages", headers=leader_headers)
    assert b"Direct note" in leader_history.data


def test_leader_can_archive_message_until_fiscal_year_end(client, leader_headers, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    client.post(
        "/admin/messages",
        data={
            "delivery": "broadcast",
            "audience": "community_user",
            "subject": "Archive me",
            "body": "Temporary notice.",
        },
        headers=leader_headers,
    )
    with app.app_context():
        message = Message.query.filter_by(subject="Archive me").one()
        message_id = message.id

    response = client.post(f"/admin/messages/{message_id}/archive", headers=leader_headers)

    assert response.status_code == 302
    with app.app_context():
        message = db.session.get(Message, message_id)
        assert message.archived_at is not None
        assert str(message.retain_until) == f"{date.today().year}-12-31"

    member_inbox = client.get("/my/messages", headers=member_headers)
    assert b"Archive me" not in member_inbox.data

    leader_history = client.get("/admin/messages", headers=leader_headers)
    assert b"Archive me" in leader_history.data
    assert f"Archived until {date.today().year}-12-31".encode() in leader_history.data


def test_direct_message_requires_existing_member_email(client, leader_headers):
    response = client.post(
        "/admin/messages",
        data={
            "delivery": "direct",
            "recipient_email": "missing@example.test",
            "subject": "Missing",
            "body": "No recipient.",
        },
        headers=leader_headers,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"recipient_email must match an existing member" in response.data


def test_member_cannot_use_admin_messaging(client, member_headers):
    response = client.post(
        "/admin/messages",
        data={"delivery": "broadcast", "audience": "community_user", "subject": "Bad broadcast", "body": "Nope"},
        headers=member_headers,
    )

    assert response.status_code == 403


def test_leader_cannot_create_admin_from_ui(client, leader_headers, app):
    response = client.post(
        "/members",
        data={
            "email": "ui-admin@example.test",
            "name": "UI Admin",
            "role": "admin",
            "status": "pending",
        },
        headers=leader_headers,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"only admins can assign the admin role" in response.data
    with app.app_context():
        assert User.query.filter_by(email="ui-admin@example.test").one_or_none() is None


def test_ui_rejects_invalid_vote_dates(client, leader_headers, app):
    response = client.post(
        "/voting",
        data={
            "title": "Bad dates",
            "open_date": "2026-01-02",
            "close_date": "2026-01-01",
            "option_1": "Yes",
            "option_2": "No",
        },
        headers=leader_headers,
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"close_date must be on or after open_date" in response.data
    with app.app_context():
        assert Vote.query.filter_by(title="Bad dates").one_or_none() is None


def test_member_message_form_only_targets_leadership(client, member_headers):
    response = client.get("/my/messages", headers=member_headers)

    assert response.status_code == 200
    assert b"Send to leadership" in response.data
    assert b"Direct recipient" not in response.data
    assert b"Audience" not in response.data


def test_admin_can_export_and_anonymize_user(client, admin_headers, member_headers, app):
    client.get("/dashboard", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        member_id = member.id

    export_response = client.get(f"/admin/compliance/users/{member_id}/export", headers=admin_headers)

    assert export_response.status_code == 200
    assert export_response.mimetype == "application/json"
    assert b"member@example.test" in export_response.data

    response = client.post(f"/admin/compliance/users/{member_id}/anonymize", headers=admin_headers)

    assert response.status_code == 302
    with app.app_context():
        member = db.session.get(User, member_id)
        assert member.email == f"deleted-user-{member_id}@deleted.local"
        assert member.name == "Deleted User"


def test_admin_reports_csv(client, admin_headers):
    response = client.get("/admin/reports/members.csv", headers=admin_headers)

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b"id,email,name,role,status,dob" in response.data


def db_value(key: str) -> str:
    setting = Setting.query.filter_by(key=key).one()
    return setting.value
