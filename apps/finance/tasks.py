from __future__ import annotations

from celery import shared_task
from django.core.exceptions import ValidationError

from apps.finance.services import dispatch_scheduled_fee_reminders, verify_gateway_payment_by_reference


@shared_task(name="finance.send_scheduled_fee_reminders")
def send_scheduled_fee_reminders(days_ahead=3):
    return dispatch_scheduled_fee_reminders(days_ahead=days_ahead)


@shared_task(name="finance.verify_gateway_reference")
def verify_gateway_reference(reference):
    try:
        transaction_row, payment, receipt = verify_gateway_payment_by_reference(reference=reference)
    except ValidationError as exc:
        return {"ok": False, "reference": reference, "error": "; ".join(exc.messages)}
    return {
        "ok": True,
        "reference": transaction_row.reference,
        "status": transaction_row.status,
        "payment_id": payment.id if payment else None,
        "receipt_id": str(receipt.id) if receipt else None,
    }
