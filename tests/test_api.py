from __future__ import annotations

from datetime import date, timedelta

from funeral_fund.extensions import db
from funeral_fund.models import User, Vote, VoteCast, VoteOption


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


def test_member_cannot_vote_twice(client, member_headers, app):
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
        vote.options.append(VoteOption(label="No"))
        db.session.add(vote)
        db.session.commit()
        vote_id = vote.id
        option_id = vote.options[0].id

    first = client.post(
        f"/api/votes/{vote_id}/cast",
        json={"option_id": option_id},
        headers=member_headers,
    )
    second = client.post(
        f"/api/votes/{vote_id}/cast",
        json={"option_id": option_id},
        headers=member_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.get_json()["error"] == "member has already voted"


def test_vote_option_must_belong_to_vote(client, member_headers, app):
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
        other_vote = Vote(
            title="Officers",
            open_date=date.today() - timedelta(days=1),
            close_date=date.today() + timedelta(days=1),
        )
        vote.options.append(VoteOption(label="Yes"))
        other_vote.options.append(VoteOption(label="Chair"))
        db.session.add_all([vote, other_vote])
        db.session.commit()
        vote_id = vote.id
        wrong_option_id = other_vote.options[0].id

    response = client.post(
        f"/api/votes/{vote_id}/cast",
        json={"option_id": wrong_option_id},
        headers=member_headers,
    )

    assert response.status_code == 400
    with app.app_context():
        assert VoteCast.query.count() == 0


def test_member_without_dob_cannot_vote(client, member_headers, app):
    client.get("/", headers=member_headers)
    with app.app_context():
        member = User.query.filter_by(email="member@example.test").one()
        member.status = "active"
        member.dob = None
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

    assert response.status_code == 403


def test_votes_require_two_options(client, leader_headers):
    response = client.post(
        "/api/votes",
        json={
            "title": "Budget",
            "open_date": "2026-01-01",
            "close_date": "2026-01-02",
            "options": ["Yes"],
        },
        headers=leader_headers,
    )

    assert response.status_code == 400


def test_create_member_validates_required_email(client, leader_headers):
    response = client.post("/api/members", json={"name": "Missing Email"}, headers=leader_headers)

    assert response.status_code == 400
    assert "email" in response.get_json()["error"]


def test_payment_requires_positive_decimal_amount(client, member_headers):
    client.get("/", headers=member_headers)

    response = client.post(
        "/api/payments/initiate",
        json={"amount": "-1.00"},
        headers=member_headers,
    )

    assert response.status_code == 400
