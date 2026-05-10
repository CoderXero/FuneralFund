from __future__ import annotations

from datetime import date

from funeral_fund.extensions import db
from funeral_fund.models import FamilyMember, User
from funeral_fund.services import age_out_dependants, membership_status


def test_membership_status_thresholds():
    assert membership_status(0) == "active"
    assert membership_status(30) == "active"
    assert membership_status(31) == "late"
    assert membership_status(60) == "late"
    assert membership_status(61) == "suspended"


def test_age_out_dependants_converts_dependant_to_pending_member(app):
    with app.app_context():
        user = User(email="parent@example.test", name="Parent", role="community_user", status="active")
        db.session.add(user)
        db.session.flush()
        dependant = FamilyMember(
            user_id=user.id,
            name="Adult Child",
            category="dependant",
            email="Adult.Child@Example.Test",
            dob=date(2000, 1, 1),
        )
        db.session.add(dependant)
        db.session.commit()

        converted = age_out_dependants(today=date(2026, 1, 1))
        db.session.commit()

        assert [member.id for member in converted] == [dependant.id]
        assert dependant.category == "pending_member"
        assert dependant.status == "pending"
        converted_user = db.session.get(User, dependant.converted_user_id)
        assert converted_user.email == "adult.child@example.test"
        assert converted_user.status == "pending"
