"""Deterministic extractor for stable, labeled invoice layouts (first rung of the ladder)."""
import re

from backends import money
from validation import PO_RE, INVOICE_RE, PAYEE_RE, TOTAL_RE, AMOUNT_RE, printed_charge_rows, validate_extraction


def rules_extract(client, invoice_text, email_text="", trace=None):
    """Generic labeled fields and tabular charge rows; no fixture IDs or gold access."""
    trace = trace if trace is not None else {}
    trace.update(status="failed", attempts=1, repair_used=False, method="regex")
    def unique(pattern):
        values = list(dict.fromkeys(pattern.findall(invoice_text)))
        if len(values) != 1:
            raise ValueError("Rules extractor requires one unambiguous labeled value")
        return values[0].strip()
    total_line = unique(TOTAL_RE)
    amounts = AMOUNT_RE.findall(total_line)
    if len(amounts) != 1:
        raise ValueError("Rules total is missing or ambiguous")
    fields = {"po_number": unique(PO_RE), "invoice_number": unique(INVOICE_RE),
              "vendor_name": unique(PAYEE_RE), "invoice_amount": str(money(amounts[0].replace(",", ""))),
              "currency": unique(re.compile(r"\b(?:USD|EUR|CAD|GBP|JPY|AUD|CHF)\b")), "line_items": []}
    # Numbered rows, or a description separated from money by a table-sized gap.
    for _line, description, amount in printed_charge_rows(invoice_text):
        fields["line_items"].append({"description": description,
                                     "amount": str(money(amount.replace(",", "")))})
    errors = validate_extraction(fields, invoice_text, email_text)
    if errors:
        trace["validation_errors"] = errors
        raise ValueError("; ".join(errors))
    trace["status"] = "ok"
    return fields, trace
