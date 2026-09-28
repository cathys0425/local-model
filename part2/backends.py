"""Mock AP backends for a mid-market freight broker exception queue."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


PURCHASE_ORDERS: dict[str, dict[str, Any]] = {
    "PO-4821": {
        "po_number": "PO-4821",
        "vendor": "ABC Logistics",
        "amount": 12000.0,
        "currency": "USD",
        "lane": "Chicago, IL -> Dallas, TX",
        "service": "FTL dry van",
        "status": "open",
        "rate_confirmation": {
            "contracted": ["linehaul", "fuel_surcharge"],
            "accessorials": {"detention": "signed in/out times", "lumper": "lumper receipt",
                             "tolls": "toll and scale receipts"},
        },
    },
    "PO-5502": {
        "po_number": "PO-5502",
        "vendor": "Harbor Line Haul",
        "amount": 8300.0,
        "currency": "USD",
        "lane": "Newark, NJ -> Atlanta, GA",
        "service": "FTL dry van",
        "status": "open",
        "rate_confirmation": {
            "contracted": ["linehaul", "fuel_surcharge"],
            "accessorials": {"detention": "signed in/out times", "lumper": "lumper receipt",
                             "tolls": "toll and scale receipts", "stop_off": "signed delivery receipt for each stop"},
        },
    },
    "PO-6104": {
        "po_number": "PO-6104",
        "vendor": "Midwest Drayage LLC",
        "amount": 4500.0,
        "currency": "USD",
        "lane": "Joliet, IL terminal dray",
        "service": "drayage",
        "status": "paid",
        "rate_confirmation": {
            "contracted": ["linehaul", "fuel_surcharge"],
            "accessorials": {"tolls": "toll and scale receipts"},
        },
    },
}

VENDORS: dict[str, dict[str, Any]] = {
    "ABC Logistics": {
        "vendor_id": "V-100",
        "legal_name": "ABC Logistics",
        "aliases": ["ABC Logistics Inc", "ABC Logistics, Inc.", "A.B.C. Logistics"],
        "ap_contact": "billing@abclogistics.example",
        "payment_terms": "Net 30",
        "tolerance_usd": "100.00",
    },
    "Harbor Line Haul": {
        "vendor_id": "V-204",
        "legal_name": "Harbor Line Haul",
        "aliases": ["Harbor Linehaul", "Harbor Line Haul LLC"],
        "ap_contact": "invoices@harborline.example",
        "payment_terms": "Net 21",
        "tolerance_usd": "100.00",
    },
    "Midwest Drayage LLC": {
        "vendor_id": "V-318",
        "legal_name": "Midwest Drayage LLC",
        "aliases": ["Midwest Drayage"],
        "ap_contact": "ap@midwestdray.example",
        "payment_terms": "Net 15",
        "tolerance_usd": "100.00",
    },
}


PAID_INVOICES = [
    {"vendor_id": "V-318", "invoice_number": "INV-6104", "po_number": "PO-6104",
     "amount": "4500.00", "paid_on": "2026-09-01"},
]


def money(value: Any) -> Decimal:
    """Finite, nonnegative cent amounts only; never round or salvage input."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("amount must be a decimal number")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("999999999999.99"):
        raise ValueError("amount must be finite, nonnegative and within supported range")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("amount has more than two decimal places")
    return amount.quantize(Decimal("0.01"))


def _normalize_name(name: str | None) -> str:
    # Punctuation/spacing are harmless; legal suffixes require an explicit alias.
    if not isinstance(name, str):
        return ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.casefold()).split())


def names_match(left: str | None, right: str | None) -> bool:
    a, b = _normalize_name(left), _normalize_name(right)
    return bool(a and b and a == b)


def lookup_purchase_order(po_number: str | None) -> dict[str, Any]:
    if not isinstance(po_number, str) or not po_number.strip():
        return {"error": "missing_po_number"}
    key = po_number.strip().upper()
    record = PURCHASE_ORDERS.get(key)
    return dict(record) if record else {"error": f"{key} not found"}


def lookup_vendor(vendor_name: str | None) -> dict[str, Any]:
    matches = [record for name, record in VENDORS.items()
               if any(names_match(vendor_name, candidate)
                      for candidate in [name, *record.get("aliases", [])])]
    if len(matches) != 1:
        return {"error": "vendor missing or ambiguous"}
    return dict(matches[0])


def vendors_match(invoice_vendor: str | None, po_vendor: str | None) -> bool:
    if names_match(invoice_vendor, po_vendor):
        return True
    left, right = lookup_vendor(invoice_vendor), lookup_vendor(po_vendor)
    return bool(left.get("vendor_id") and left.get("vendor_id") == right.get("vendor_id"))


def lookup_paid_invoice(invoice_number: str, vendor_id: str) -> dict[str, Any] | None:
    # Invoice numbers are unique within a vendor, not across all vendors.
    for record in PAID_INVOICES:
        if (record["vendor_id"] == vendor_id
                and record["invoice_number"].casefold() == invoice_number.casefold()):
            return dict(record)
    return None


# Freight charge vocabulary. Unrecognized wording is never guessed into a category.
CHARGE_CATEGORIES = [
    ("fuel_surcharge", re.compile(r"\bfuel\b")),
    ("linehaul", re.compile(r"\bline ?haul\b")),
    ("detention", re.compile(r"\bdetention\b")),
    ("lumper", re.compile(r"\blumper\b")),
    ("tolls", re.compile(r"\btolls?\b|\bscale fees?\b")),
    ("layover", re.compile(r"\blayover\b")),
    ("stop_off", re.compile(r"\bstop[- ]?off\b|\bextra stop\b")),
    ("after_hours", re.compile(r"\bafter[- ]hours\b")),
]


def classify_charge(description: str | None) -> str:
    text = description.casefold() if isinstance(description, str) else ""
    matches = [name for name, pattern in CHARGE_CATEGORIES if pattern.search(text)]
    return matches[0] if len(matches) == 1 else "unrecognized"


def review_charges(line_items: Any, po: dict[str, Any]) -> list[dict[str, Any]]:
    """Compare each printed charge with the PO's rate confirmation."""
    rate_con = po.get("rate_confirmation") or {}
    contracted = set(rate_con.get("contracted", []))
    accessorials = rate_con.get("accessorials", {})
    review = []
    for item in line_items if isinstance(line_items, list) else []:
        if not isinstance(item, dict):
            continue
        category = classify_charge(item.get("description"))
        if category in contracted:
            status, backup = "contracted", None
        elif category in accessorials:
            status, backup = "backup_required", accessorials[category]
        elif category == "unrecognized":
            status, backup = "unrecognized", None
        else:
            status, backup = "not_on_rate_confirmation", None
        review.append({"description": item.get("description"), "amount": str(item.get("amount")),
                       "category": category, "status": status, "backup": backup})
    return review


def compute_mismatch(
    invoice: dict[str, Any], po: dict[str, Any] | None,
    vendor: dict[str, Any] | None, paid: dict[str, Any] | None = None,
) -> dict[str, Any]:
    po = po if isinstance(po, dict) and "error" not in po else {}
    vendor = vendor if isinstance(vendor, dict) and "error" not in vendor else {}
    errors = []
    amounts = {}
    for key, value in (("invoice_amount", invoice.get("invoice_amount")),
                       ("po_amount", po.get("amount")),
                       ("tolerance_usd", vendor.get("tolerance_usd"))):
        try:
            amounts[key] = money(value)
        except ValueError as exc:
            amounts[key] = None
            errors.append(f"{key}: {exc}")
    total, po_total, tolerance = (amounts[k] for k in
                                ("invoice_amount", "po_amount", "tolerance_usd"))
    delta = total - po_total if total is not None and po_total is not None else None
    items = invoice.get("line_items")
    line_total = None
    if isinstance(items, list) and items:
        try:
            line_total = sum((money(item["amount"]) for item in items), Decimal("0.00"))
        except (KeyError, TypeError, ValueError):
            errors.append("invalid line item amount")
    currency = invoice.get("currency")
    return {
        "po_found": bool(po), "vendor_found": bool(vendor.get("vendor_id")),
        "vendor_matches_po": vendors_match(invoice.get("vendor_name"), po.get("vendor")),
        "currency_matches": bool(currency and po.get("currency") and currency == po["currency"]),
        # This demo's policies are denominated in USD. Other currencies need a policy.
        "policy_found": bool(vendor.get("vendor_id") and tolerance is not None and currency == "USD"),
        **{key: str(value) if value is not None else None for key, value in amounts.items()},
        "amount_delta": str(delta) if delta is not None else None,
        "within_tolerance": delta is not None and tolerance is not None and abs(delta) <= tolerance,
        "line_items_total": str(line_total) if line_total is not None else None,
        "line_items_match": line_total is not None and line_total == total,
        "already_paid": bool(paid), "prior_payment": paid, "po_status": po.get("status"),
        "charge_review": review_charges(items, po) if po else [],
        "validation_errors": errors,
    }


def draft_vendor_email(
    invoice: dict[str, Any],
    mismatch: dict[str, Any],
    recommended_action: str,
    exception_type: str | None = None,
) -> str:
    """Template email. Numbers and charge lists come from code, not the model."""
    invoice_no = invoice.get("invoice_number") or "(unknown invoice)"
    po_no = invoice.get("po_number") or "(unknown PO)"
    vendor = invoice.get("vendor_name") or "vendor"
    invoice_amount = mismatch.get("invoice_amount")
    po_amount = mismatch.get("po_amount")
    delta = mismatch.get("amount_delta")
    charges = mismatch.get("charge_review") or []
    unapproved = [c for c in charges if c["status"] in ("not_on_rate_confirmation", "unrecognized")]
    backup = [c for c in charges if c["status"] == "backup_required"]
    requests = ""
    if unapproved:
        requests += ("\nThese charges are not on the rate confirmation for this load:\n"
                     + "".join(f"- {c['description']}: {c['amount']}\n" for c in unapproved)
                     + "Please send a signed rate confirmation amendment or remove them.\n")
    if backup:
        requests += ("\nPlease send backup for these accessorial charges:\n"
                     + "".join(f"- {c['description']} {c['amount']}: {c['backup']}\n" for c in backup))
    signature = "\nRegards,\nAccounts Payable\nNorthline Freight Brokerage"

    if recommended_action == "short_pay":
        return (
            f"Subject: Short-pay notice for {invoice_no} / {po_no}\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"We received invoice {invoice_no} for {invoice_amount} "
            f"against {po_no} at {po_amount}. "
            f"The variance is {delta}.\n\n"
            f"AP proposes paying the purchase order amount of {po_amount}, subject to human approval. "
            f"No payment has been approved.\n"
            f"{requests}{signature}"
        )

    if recommended_action == "request_information" and exception_type == "unauthorized_charge":
        return (
            f"Subject: Charges to confirm on {invoice_no} / {po_no}\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"Invoice {invoice_no} is on hold until the charges below are confirmed.\n"
            f"{requests}{signature}"
        )

    if recommended_action == "request_information":
        return (
            f"Subject: Need backup for {invoice_no}\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"We cannot match invoice {invoice_no} to an active purchase order "
            f"({po_no}). Please send the signed rate confirmation or a valid PO number.\n"
            f"{signature}"
        )

    if recommended_action == "escalate":
        return (
            f"Subject: Invoice {invoice_no} held for review\n\n"
            f"Hello {vendor} billing team,\n\n"
            f"Invoice {invoice_no} is on hold pending internal review. "
            f"We will follow up after AP completes exception handling.\n"
            f"{signature}"
        )

    return (
        f"Subject: Invoice {invoice_no} matched to {po_no}\n\n"
        f"Hello {vendor} billing team,\n\n"
        f"Invoice {invoice_no} is within the tolerance for {po_no} and awaits human approval.\n"
        f"{requests}{signature}"
    )
