from django import template

from apps.finance.models import PaymentGatewayTransaction, PaymentMethod

register = template.Library()


def _plan_payload(obj):
    if obj is None:
        return {}
    metadata = {}
    if isinstance(obj, PaymentGatewayTransaction):
        metadata = obj.metadata or {}
    else:
        gateway_txn = getattr(obj, "gateway_transaction", None)
        if gateway_txn is not None:
            metadata = gateway_txn.metadata or {}
    payload = metadata.get("payment_plan") if isinstance(metadata, dict) else {}
    return payload if isinstance(payload, dict) else {}


@register.filter
def payment_plan_label(obj):
    payload = _plan_payload(obj)
    label = (payload.get("label") or "").strip()
    if label:
        return label

    code = (payload.get("payment_plan") or "").strip().upper()
    if code == "FEE_ITEM":
        fee_item = (payload.get("fee_item") or "").strip()
        return fee_item if fee_item else "Posted fee item"

    payment_method = getattr(obj, "payment_method", "")
    if payment_method == PaymentMethod.GATEWAY:
        return "Gateway payment"
    return "Manual payment"


@register.filter
def payment_plan_summary(obj):
    payload = _plan_payload(obj)
    code = (payload.get("payment_plan") or "").strip().upper()
    fee_item = (payload.get("fee_item") or "").strip()

    if code == "FEE_ITEM" and fee_item:
        return f"Recorded against: {fee_item}."
    if getattr(obj, "payment_method", "") == PaymentMethod.GATEWAY:
        return "Recorded through an online payment gateway."
    return "Recorded directly by the bursar."


@register.filter
def naira(value):
    if value in (None, ""):
        return "0.00"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)
