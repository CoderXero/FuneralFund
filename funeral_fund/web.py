from __future__ import annotations

from flask import Blueprint, render_template

from .auth import current_user
from .models import Payment, User, Vote

web_bp = Blueprint("web", __name__)


@web_bp.get("/")
def dashboard():
    user = current_user()
    return render_template(
        "dashboard.html",
        user=user,
        member_count=User.query.count(),
        pending_count=User.query.filter_by(status="pending").count(),
        payment_count=Payment.query.count(),
        vote_count=Vote.query.count(),
    )


@web_bp.get("/members")
def members_page():
    current_user()
    return render_template("members/index.html", members=User.query.order_by(User.created_at.desc()).all())


@web_bp.get("/payments")
def payments_page():
    current_user()
    return render_template("payments/index.html", payments=Payment.query.order_by(Payment.created_at.desc()).all())


@web_bp.get("/voting")
def voting_page():
    current_user()
    return render_template("voting/index.html", votes=Vote.query.order_by(Vote.created_at.desc()).all())
