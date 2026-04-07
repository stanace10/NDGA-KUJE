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
    if code == "FULL":
        return "Full outstanding bundle"
    if code == "FEE_ITEM":
        fee_item = (payload.get("fee_item") or "").strip()
        return f"{fee_item} only" if fee_item else "Single fee item"
    if code == "PERCENTAGE":
        percentage = payload.get("percentage")
        return f"{percentage}% of outstanding balance" if percentage else "Percentage payment"
    if code == "CUSTOM":
        return "Custom amount"

    payment_method = getattr(obj, "payment_method", "")
    if payment_method == PaymentMethod.GATEWAY:
        return "Gateway payment"
    return "Manual payment"


@register.filter
def payment_plan_summary(obj):
    payload = _plan_payload(obj)
    code = (payload.get("payment_plan") or "").strip().upper()
    fee_item = (payload.get("fee_item") or "").strip()
    percentage = payload.get("percentage")

    if code == "FEE_ITEM" and fee_item:
        return f"Paying only: {fee_item}"
    if code == "PERCENTAGE" and percentage:
        return f"Split plan: {percentage}% of total outstanding"
    if code == "FULL":
        return "Clears the full outstanding balance in one payment."
    if code == "CUSTOM":
        return "Custom amount chosen by bursar or student."
    if getattr(obj, "payment_method", "") == PaymentMethod.GATEWAY:
        return "Recorded through an online payment gateway."
    return "Recorded directly by the bursar."
