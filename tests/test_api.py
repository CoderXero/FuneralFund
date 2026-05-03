from __future__ import annotations

from datetime import date, timedelta

from funeral_fund.extensions import db
from funeral_fund.models import User, Vote, VoteOption


def test_leader_can_create_and_approve_member(client, leader_headers):
    response = client.post(
        "/api/members",
        json={"email": "new@example.test", "name": "New Member", "dob": "1990-01-01"},
        headers=leader_headers,
    )

    assert response.status_code == 201
    member_id = response.get_json()["id"]

    response = client.post(f"/api/members/{member_id}/approve", headers=leader_headers)

    assert response.status_code == 200
    assert response.get_json()["status"] == "active"


def test_member_cannot_create_another_member(client, member_headers):
    response = client.post(
        "/api/members",
        json={"email": "blocked@example.test", "name": "Blocked"},
        headers=member_headers,
    )

    assert response.status_code == 403


def test_payment_manual_proof_and_verification(client, leader_headers, member_headers, app):
    client.get("/", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        member.status = "active"
        db.session.commit()
        member_id = member.id

    response = client.post(
        "/api/payments/initiate",
        json={"member_id": member_id, "amount": "25.00", "method": "zelle"},
        headers=member_headers,
    )

    assert response.status_code == 201
    payment_id = response.get_json()["id"]

    response = client.post(
        "/api/payments/proof",
        json={"payment_id": payment_id, "transaction_id": "TX123", "notes": "Paid"},
        headers=member_headers,
    )
    assert response.status_code == 200

    response = client.post(
        "/api/payments/verify",
        json={"payment_id": payment_id, "status": "verified"},
        headers=leader_headers,
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "verified"


def test_active_adult_member_can_vote_once(client, member_headers, app):
    client.get("/", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        member.status = "active"
        member.dob = date(1990, 1, 1)
        vote = Vote(
            title="Budget",
            open_date=date.today() - timedelta(days=1),
            close_date=date.today() + timedelta(days=1),
        )
        vote.options.append(VoteOption(label="Yes"))
        db.session.add(vote)
        db.session.commit()
        vote_id = vote.id
        option_id = vote.options[0].id

    response = client.post(
        f"/api/votes/{vote_id}/cast",
        json={"option_id": option_id},
        headers=member_headers,
    )

    assert response.status_code == 201
