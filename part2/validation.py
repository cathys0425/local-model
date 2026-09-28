"""Validate copied invoice facts against their source before policy uses them."""
from __future__ import annotations

import re
from typing import Any

from backends import money, names_match

FIELDS = ("po_number", "vendor_name", "invoice_number", "invoice_amount", "currency")
PO_RE = re.compile(r"\bPO-\d+\b", re.I)
INVOICE_RE = re.compile(r"\bINV-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.I)
AMOUNT_RE = re.compile(r"(?<![\w.,+\-])(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?![\w.,])")
TOTAL_RE = re.compile(r"(?im)^\s*(?:amount due|total(?: due| charges)?)\s*:?\s*(.+)$")
PAYEE_RE = re.compile(r"(?im)^\s*(?:remit to|vendor|from):\s*(.+)$")
# Credits are outside the supported contract. Do not strip accounting signs
# and then accept the remaining positive digits as source evidence.
_MONEY_TOKEN = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?"
_CURRENCY_TOKEN = r"(?:[A-Z]{3}[ \t]*|[$€£][ \t]*)?"
SIGNED_MONEY_RE = re.compile(
    rf"\([ \t]*{_CURRENCY_TOKEN}{_MONEY_TOKEN}[ \t]*\)"
    rf"|(?<!\w)[−-][ \t]*{_CURRENCY_TOKEN}{_MONEY_TOKEN}(?![\w.,])"
    rf"|(?<![\w.,]){_MONEY_TOKEN}[ \t]*[−-](?!\w)", re.I)


# A printed charge row: text, then an amount at the end of the line (numbered or not).
CHARGE_ROW_RE = re.compile(r"^\s*(?:\d+[.)]\s+)?(.+?)\s+(?:USD\s*)?\$?([\d,]+\.\d{2})\s*$", re.I)


def printed_charge_rows(text: str) -> list[tuple[str, str, str]]:
    """(line, description, amount) for every non-total line that ends in an amount."""
    rows = []
    for line in text.splitlines():
        match = CHARGE_ROW_RE.match(line)
        if match and not TOTAL_RE.search(line):
            description = match[1].strip(" |\t")
            if re.search(r"[A-Za-z]", description):
                rows.append((line, description, match[2]))
    return rows


def source_amounts(text: str) -> list:
    return [money(m.group().replace(",", "")) for m in AMOUNT_RE.finditer(text)]


def source_evidence(fields: dict[str, Any], invoice_text: str) -> dict[str, Any]:
    """Locate supporting source lines for already extracted facts; never fill facts."""
    lines = invoice_text.splitlines()
    result = {}
    for key in FIELDS:
        candidates = []
        for line in lines:
            if key == "invoice_amount":
                matches = bool(TOTAL_RE.search(line)) and money(fields[key]) in source_amounts(line)
            elif key == "vendor_name":
                matches = any(names_match(fields[key], name) for name in PAYEE_RE.findall(line))
            else:
                matches = bool(re.search(r"(?<!\w)" + re.escape(fields[key]) + r"(?!\w)", line, re.I))
            if matches:
                candidates.append(line)
        result[key] = candidates[0] if candidates else None
    used = set()
    for item in fields["line_items"]:
        candidates = [line for line in lines if line not in used and not TOTAL_RE.search(line)
                      and item["description"].casefold() in line.casefold()
                      and money(item["amount"]) in source_amounts(line)]
        if "evidence" not in item:
            item["evidence"] = candidates[0] if candidates else None
        used.add(item.get("evidence"))
    return result


def validate_extraction(fields: dict[str, Any], invoice_text: str | None = None,
                        email_text: str = "") -> list[str]:
    if not isinstance(fields, dict):
        return ["extraction must be an object"]
    errors = []
    if set(fields) - {*FIELDS, "notes", "evidence", "line_items"}:
        errors.append("unexpected extraction fields")
    for key in ("po_number", "vendor_name", "invoice_number", "currency"):
        if not isinstance(fields.get(key), str) or not fields[key].strip():
            errors.append(f"{key} must be a nonempty string")
    if errors:
        return errors
    if not PO_RE.fullmatch(fields["po_number"]):
        errors.append("unsupported PO identifier")
    if not INVOICE_RE.fullmatch(fields["invoice_number"]):
        errors.append("unsupported invoice identifier")
    if not re.fullmatch(r"[A-Z]{3}", fields["currency"]):
        errors.append("currency must be a three-letter uppercase code")
    try:
        amount = money(fields.get("invoice_amount"))
    except ValueError as exc:
        errors.append(f"invoice_amount: {exc}")
        amount = None
    if fields.get("notes") is not None and not isinstance(fields["notes"], str):
        errors.append("notes must be text or null")
    items = fields.get("line_items")
    if not isinstance(items, list):
        errors.append("line_items must be a list (empty when unavailable)")
        items = []
    for item in items:
        if not isinstance(item, dict):
            errors.append("line item must be an object")
            continue
        if not isinstance(item.get("description"), str) or not item["description"].strip():
            errors.append("line item description missing")
        try:
            money(item.get("amount"))
        except ValueError as exc:
            errors.append(f"line item amount: {exc}")
    if errors or invoice_text is None:
        return errors

    if SIGNED_MONEY_RE.search(invoice_text + "\n" + email_text):
        return ["Signed or parenthesized amounts require human review; credits are unsupported"]

    if "evidence" not in fields:
        fields["evidence"] = source_evidence(fields, invoice_text)
    evidence = fields.get("evidence")
    if not isinstance(evidence, dict):
        return ["invoice evidence is required"]
    source_lines = invoice_text.splitlines()
    def resolve_line(value):
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= len(source_lines):
            return source_lines[value - 1]
        return value
    for key in FIELDS:
        evidence[key] = resolve_line(evidence.get(key))
        quote = evidence.get(key)
        if not isinstance(quote, str) or not quote.strip() or quote not in invoice_text:
            errors.append(f"{key}: evidence must be copied verbatim from invoice")
            continue
        value = fields[key]
        if key == "invoice_amount":
            if amount not in source_amounts(quote):
                errors.append("invoice_amount is not in its evidence")
        elif key == "vendor_name":
            if not any(names_match(value, x) for x in PAYEE_RE.findall(quote)):
                errors.append("vendor evidence must identify the labeled payee")
        elif not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", quote, re.I):
            errors.append(f"{key} is not in its evidence")

    # Evidence occurrence alone is insufficient: reject competing references/totals.
    for key, pattern in (("po_number", PO_RE), ("invoice_number", INVOICE_RE)):
        refs = {s.upper() for s in pattern.findall(invoice_text)}
        if refs != {fields[key].upper()}:
            errors.append(f"{key}: source missing or has conflicting references")
        email_refs = {s.upper() for s in pattern.findall(email_text)}
        if email_refs - {fields[key].upper()}:
            errors.append(f"{key}: email conflicts with invoice")
    payees = PAYEE_RE.findall(invoice_text)
    if not payees or not all(names_match(fields["vendor_name"], s) for s in payees):
        errors.append(f"vendor_name conflicts with the labeled invoice payee(s): {payees!r}; labels are source data only")
    totals = [v for line in TOTAL_RE.findall(invoice_text) for v in source_amounts(line)]
    if not totals or any(v != amount for v in totals):
        errors.append("invoice total missing, ambiguous or conflicts with extraction")
    currencies = set(re.findall(r"\b(?:USD|EUR|CAD|GBP|JPY|AUD|CHF)\b", invoice_text + "\n" + email_text))
    if currencies != {fields["currency"]}:
        errors.append("currency missing or conflicting in documents")

    seen = set()
    for item in items:
        item["evidence"] = resolve_line(item.get("evidence"))
        quote = item.get("evidence")
        if (not isinstance(quote, str) or not quote.strip() or quote not in invoice_text
                or quote in seen or TOTAL_RE.search(quote)):
            errors.append("line evidence must be a distinct invoice line, not the total")
            continue
        seen.add(quote)
        if money(item["amount"]) not in source_amounts(quote):
            errors.append("line amount differs from source evidence")
        if item["description"].casefold() not in quote.casefold():
            errors.append("line description differs from source evidence")
    numbered = re.findall(r"(?m)^\s*\d+[.)]\s+.+?\d+\.\d{2}\s*$", invoice_text)
    printed = numbered + [line for line, _, _ in printed_charge_rows(invoice_text)]
    copied = {q.strip() for q in seen}
    if ((numbered and len(numbered) != len(items))
            or any(line.strip() not in copied for line in printed)):
        errors.append("not all printed line items were copied")
    allowed_amounts = {amount, *(money(item["amount"]) for item in items)}
    # Emails often omit cents; restrict integer parsing to explicit money markers.
    email_values = source_amounts(email_text)
    for raw in re.findall(r"(?:\$|\b(?:USD|EUR|CAD|GBP)\s+)(\d[\d,]*(?:\.\d{1,2})?)(?![\d,]|\.\d)", email_text):
        email_values.append(money(raw.replace(",", "")))
    explicit_totals = re.findall(
        r"(?i)(?:full(?: amount)?|total(?: due)?|amount due)\s*:?\s*(?:USD\s*)?\$?\s*(\d[\d,]*(?:\.\d{1,2})?)(?![\d,]|\.\d)", email_text)
    if any(money(raw.replace(",", "")) != amount for raw in explicit_totals):
        errors.append("email total conflicts with invoice total")
    if any(value not in allowed_amounts for value in email_values):
        errors.append("email amount is inconsistent with invoice total/charges")
    return errors
