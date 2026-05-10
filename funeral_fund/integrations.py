from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Any

from flask import current_app

from .models import AuditLog, Payment, User


class IntegrationNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    external_id: str
    status: str
    metadata: dict[str, Any]


class PaymentProviderClient:
    def __init__(self, provider: str):
        self.provider = provider

    @property
    def base_url(self) -> str:
        return current_app.config[f"PAYMENT_{self.provider.upper()}_API_BASE_URL"]

    @property
    def api_key(self) -> str:
        return current_app.config[f"PAYMENT_{self.provider.upper()}_API_KEY"]

    def ensure_configured(self) -> None:
        if not self.base_url or not self.api_key:
            raise IntegrationNotConfigured(f"{self.provider} payment API is not configured")

    def initiate_payment(self, payment: Payment) -> ProviderResult:
        self.ensure_configured()
        return ProviderResult(
            provider=self.provider,
            external_id=f"{self.provider}-{payment.id}",
            status="pending",
            metadata={"amount": str(payment.amount)},
        )

    def verify_webhook(self, signature: str | None) -> None:
        secret = current_app.config[f"PAYMENT_{self.provider.upper()}_WEBHOOK_SECRET"]
        if not secret:
            raise IntegrationNotConfigured(f"{self.provider} webhook secret is not configured")
        if not signature:
            raise PermissionError("payment webhook signature is missing")


class WhatsAppClient:
    def ensure_configured(self) -> None:
        if not current_app.config["WHATSAPP_API_URL"] or not current_app.config["WHATSAPP_API_TOKEN"]:
            raise IntegrationNotConfigured("WhatsApp API is not configured")

    def send_message(self, to_number: str, body: str) -> ProviderResult:
        self.ensure_configured()
        return ProviderResult(
            provider="whatsapp",
            external_id=f"whatsapp:{to_number}",
            status="queued",
            metadata={"body_length": len(body)},
        )


class BlobStorageClient:
    def ensure_configured(self) -> None:
        if not current_app.config["AZURE_STORAGE_CONNECTION_STRING"]:
            raise IntegrationNotConfigured("Azure Blob Storage is not configured")

    def signed_upload_url(self, blob_name: str) -> str:
        self.ensure_configured()
        return f"azure://pending-upload/{blob_name}"


class ReportExporter:
    def monthly_payments_csv(self) -> bytes:
        rows = Payment.query.order_by(Payment.created_at.desc()).all()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "member_id", "method", "amount", "status", "created_at", "verified_at"])
        for payment in rows:
            writer.writerow(
                [
                    payment.id,
                    payment.member_id,
                    payment.method,
                    payment.amount,
                    payment.status,
                    payment.created_at.isoformat(),
                    payment.verified_at.isoformat() if payment.verified_at else "",
                ]
            )
        return buffer.getvalue().encode("utf-8")

    def members_csv(self) -> bytes:
        rows = User.query.order_by(User.created_at.desc()).all()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "email", "name", "role", "status", "dob"])
        for user in rows:
            writer.writerow([user.id, user.email, user.name, user.role, user.status, user.dob or ""])
        return buffer.getvalue().encode("utf-8")

    def audit_csv(self) -> bytes:
        rows = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "actor_id", "action", "target_type", "target_id", "metadata_json", "timestamp"])
        for log in rows:
            writer.writerow(
                [log.id, log.actor_id or "", log.action, log.target_type, log.target_id, log.metadata_json, log.timestamp]
            )
        return buffer.getvalue().encode("utf-8")
