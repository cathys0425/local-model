"""Mock AP backends for a mid-market freight broker exception queue."""

from __future__ import annotations

import re
from typing import Any


PURCHASE_ORDERS: dict[str, dict[str, Any]] = {
    "PO-4821": {
        "po_number": "PO-4821",
        "vendor": "ABC Logistics",
        "amount": 12000.0,
        "currency": "USD",
        "lane": "Chicago, IL -> Dallas, TX",
        "service": "FTL dry van",
    },
    "PO-5502": {
        "po_number": "PO-5502",
        "vendor": "Harbor Line Haul",
        "amount": 8300.0,
        "currency": "USD",
        "lane": "Newark, NJ -> Atlanta, GA",
        "service": "FTL dry van",
    },
    "PO-6104": {
        "po_number": "PO-6104",
        "vendor": "Midwest Drayage LLC",
        "amount": 4500.0,
        "currency": "USD",
        "lane": "Joliet, IL terminal dray",
        "service": "drayage",
    },
}

VENDORS: dict[str, dict[str, Any]] = {
    "ABC Logistics": {
        "vendor_id": "V-100",
        "legal_name": "ABC Logistics",
        "ap_contact": "billing@abclogistics.example",
        "payment_terms": "Net 30",
        "tolerance_usd": 1.0,
    },
    "Harbor Line Haul": {
        "vendor_id": "V-204",
        "legal_name": "Harbor Line Haul",
        "ap_contact": "invoices@harborline.example",
        "payment_terms": "Net 21",
        "tolerance_usd": 1.0,
    },
    "Midwest Drayage LLC": {
        "vendor_id": "V-318",
        "legal_name": "Midwest Drayage LLC",
        "ap_contact": "ap@midwestdray.example",
        "payment_terms": "Net 15",
        "tolerance_usd": 1.0,
    },
}


def _normalize_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = name.casefold()
    cleaned = re.sub(r"\b(llc|inc|ltd|corp|co)\b\.?", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def lookup_purchase_order(po_number: str | None) -> dict[str, Any]:
    if not po_number:
        return {"error": "missing_po_number"}
    key = po_number.strip().upper()
    record = PURCHASE_ORDERS.get(key)
    if not record:
        return {"error": f"{key} not found"}
    return dict(record)


def lookup_vendor(vendor_name: str | None) -> dict[str, Any]:
    if not vendor_name:
        return {"error": "missing_vendor_name"}
    wanted = _normalize_name(vendor_name)
    for legal_name, record in VENDORS.items():
        if _normalize_name(legal_name) == wanted:
            return dict(record)
    return {"error": f"vendor not found: {vendor_name}"}


def vendors_match(invoice_vendor: str | None, po_vendor: str | None) -> bool:
    if not invoice_vendor or not po_vendor:
        return False
    return _normalize_name(invoice_vendor) == _normalize_name(po_vendor)


def compute_mismatch(
    invoice: dict[str, Any],
    po: dict[str, Any] | None,
    vendor: dict[str, Any] | None,
) -> dict[str, Any]:
    invoice_amount = invoice.get("invoice_amount")
    po_amount = None if not po or "amount" not in po else po["amount"]
    currency_ok = True
    if po and invoice.get("currency") and po.get("currency"):
        currency_ok = invoice["currency"] == po["currency"]

    amount_delta = None
    if isinstance(invoice_amount, (int, float)) and isinstance(po_amount, (int, float)):
        amount_delta = round(float(invoice_amount) - float(po_amount), 2)

    tolerance = 1.0
    if vendor and isinstance(vendor.get("tolerance_usd"), (int, float)):
        tolerance = float(vendor["tolerance_usd"])

    vendor_ok = vendors_match(
        invoice.get("vendor_name"),
        None if not po else po.get("vendor"),
    )

    return {
        "po_found": bool(po) and "error" not in (po or {}),
        "vendor_found": bool(vendor) and "error" not in (vendor or {}),
        "vendor_matches_po": vendor_ok,
        "currency_matches": currency_ok,
        "invoice_amount": invoice_amount,
        "po_amount": po_amount,
        "amount_delta": amount_delta,
        "within_tolerance": (
            amount_delta is not None and abs(amount_delta) <= tolerance
        ),
        "tolerance_usd": tolerance,
    }


def draft_vendor_email(
    invoice: dict[str, Any],
    mismatch: dict[str, Any],
    recommended_action: str,
) -> str:
    """Template email. Numbers come from code, not the model."""
    invoice_no = invoice.get("invoice_number") or "(unknown invoice)"
    po_no = invoice.get("po_number") or "(unknown PO)"
    vendor = invoice.get("vendor_name") or "vendor"
    invoice_amount = mismatch.get("invoice_amount")
    po_amount = mismatch.get("po_amount")
    delta = mismatch.get("amount_delta")

    if recommended_action == "short_pay":
        return (
            f"Subject: Short-pay notice for {invoice_no} / {po_no}\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"We received invoice {invoice_no} for {invoice_amount} "
            f"against {po_no} at {po_amount}. "
            f"The variance is {delta}.\n\n"
            f"We will short-pay to the purchase order amount of {po_amount} "
            f"unless you send supporting backup for the variance within 5 business days.\n\n"
            f"Regards,\nAccounts Payable\nNorthline Freight Brokerage"
        )

    if recommended_action == "request_information":
        return (
            f"Subject: Need backup for {invoice_no}\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"We cannot match invoice {invoice_no} to an active purchase order "
            f"({po_no}). Please send the signed rate confirmation or a valid PO number.\n\n"
            f"Regards,\nAccounts Payable\nNorthline Freight Brokerage"
        )

    if recommended_action == "escalate":
        return (
            f"Subject: Invoice {invoice_no} held for review\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"Invoice {invoice_no} is on hold pending internal review. "
            f"We will follow up after AP completes exception handling.\n\n"
            f"Regards,\nAccounts Payable\nNorthline Freight Brokerage"
        )

    return (
        f"Subject: Invoice {invoice_no} matched to {po_no}\n\n"
        f"Hello {vendor} billing team,\n\n"
        f"Invoice {invoice_no} matches {po_no}. No vendor action is required.\n\n"
        f"Regards,\nAccounts Payable\nNorthline Freight Brokerage"
    )
