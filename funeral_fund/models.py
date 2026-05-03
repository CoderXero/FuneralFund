from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    idp_sub: Mapped[str | None] = mapped_column(unique=True, nullable=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    role: Mapped[str] = mapped_column(default="member")
    status: Mapped[str] = mapped_column(default="pending")
    dob: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    family_members: Mapped[list[FamilyMember]] = orm_relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = orm_relationship(
        "Payment", foreign_keys="Payment.member_id", back_populates="member"
    )

    @property
    def is_leadership(self) -> bool:
        return self.role in {"leader", "admin"}

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class FamilyMember(db.Model):
    __tablename__ = "family_members"
    __table_args__ = (
        CheckConstraint(
            "category in ('primary', 'secondary', 'dependant', 'relative', 'pending_member')",
            name="family_category_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    name: Mapped[str]
    category: Mapped[str]
    relationship: Mapped[str | None] = mapped_column(nullable=True)
    dob: Mapped[date | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = orm_relationship(back_populates="family_members")


class Fee(db.Model):
    __tablename__ = "fees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(db.Numeric(10, 2))
    recurring_interval: Mapped[str | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Notice(db.Model):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    notice_number: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(db.Numeric(10, 2))
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Payment(db.Model):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    fee_id: Mapped[int | None] = mapped_column(db.ForeignKey("fees.id"), nullable=True)
    notice_id: Mapped[int | None] = mapped_column(db.ForeignKey("notices.id"), nullable=True)
    method: Mapped[str]
    amount: Mapped[Decimal] = mapped_column(db.Numeric(10, 2))
    proof_url: Mapped[str | None] = mapped_column(nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="pending")
    verified_by_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    member: Mapped[User] = orm_relationship(foreign_keys=[member_id], back_populates="payments")


class Vote(db.Model):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    description: Mapped[str | None] = mapped_column(nullable=True)
    open_date: Mapped[date]
    close_date: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    options: Mapped[list[VoteOption]] = orm_relationship(
        back_populates="vote", cascade="all, delete-orphan"
    )


class VoteOption(db.Model):
    __tablename__ = "vote_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    vote_id: Mapped[int] = mapped_column(db.ForeignKey("votes.id"), index=True)
    label: Mapped[str]

    vote: Mapped[Vote] = orm_relationship(back_populates="options")


class VoteCast(db.Model):
    __tablename__ = "vote_casts"
    __table_args__ = (UniqueConstraint("vote_id", "member_id", name="one_vote_per_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vote_id: Mapped[int] = mapped_column(db.ForeignKey("votes.id"), index=True)
    option_id: Mapped[int] = mapped_column(db.ForeignKey("vote_options.id"))
    member_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Message(db.Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"), nullable=True, index=True)
    recipient_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"), nullable=True, index=True)
    audience: Mapped[str] = mapped_column(default="direct")
    subject: Mapped[str]
    body: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    sender: Mapped[User | None] = orm_relationship(foreign_keys=[sender_id])
    recipient: Mapped[User | None] = orm_relationship(foreign_keys=[recipient_id])


class Setting(db.Model):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"), nullable=True)
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    metadata_json: Mapped[str] = mapped_column(default="{}")
    timestamp: Mapped[datetime] = mapped_column(default=utcnow)
