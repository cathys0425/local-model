"""Small frozen synthetic set for testing language variation in charge descriptions."""

CASES = [
    {
        "id": "language-001",
        "po_number": "PO-4821",
        "vendor_name": "ABC Logistics",
        "invoice_number": "INV-LANG-001",
        "invoice_amount": "12450.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "12000.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "Line haul charges for the Chicago to Dallas movement: USD 12,000.00",
            "Fuel surcharge under the weekly index is USD 450.00",
        ],
    },
    {
        "id": "language-002",
        "po_number": "PO-4821",
        "vendor_name": "ABC Logistics",
        "invoice_number": "INV-LANG-002",
        "invoice_amount": "12450.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "12000.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "The carrier billed USD 12,000.00 for line haul service",
            "The additional fuel surcharge comes to USD 450.00",
        ],
    },
    {
        "id": "language-003",
        "po_number": "PO-4821",
        "vendor_name": "ABC Logistics",
        "invoice_number": "INV-LANG-003",
        "invoice_amount": "12450.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "12000.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "USD 450.00 reflects the fuel surcharge",
            "USD 12,000.00 reflects the line haul",
        ],
    },
    {
        "id": "language-004",
        "po_number": "PO-4821",
        "vendor_name": "ABC Logistics",
        "invoice_number": "INV-LANG-004",
        "invoice_amount": "12450.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "12000.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "The transportation charge (line haul) is 12000.00",
            "Index-based fuel surcharge is 450.00",
        ],
    },
    {
        "id": "language-005",
        "po_number": "PO-5502",
        "vendor_name": "Harbor Line Haul",
        "invoice_number": "INV-LANG-005",
        "invoice_amount": "8750.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "8300.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "Line haul service on the Newark to Atlanta lane was billed at USD 8,300.00",
            "The fuel surcharge adds USD 450.00 to the carrier's charge",
        ],
    },
    {
        "id": "language-006",
        "po_number": "PO-5502",
        "vendor_name": "Harbor Line Haul",
        "invoice_number": "INV-LANG-006",
        "invoice_amount": "8750.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "8300.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "The line haul portion is USD 8,300.00",
            "The fuel amount, charged as a surcharge, is USD 450.00",
        ],
    },
    {
        "id": "language-007",
        "po_number": "PO-5502",
        "vendor_name": "Harbor Line Haul",
        "invoice_number": "INV-LANG-007",
        "invoice_amount": "8750.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "8300.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "USD 450.00 was assessed for the fuel surcharge",
            "USD 8,300.00 was assessed for line haul transportation",
        ],
    },
    {
        "id": "language-008",
        "po_number": "PO-5502",
        "vendor_name": "Harbor Line Haul",
        "invoice_number": "INV-LANG-008",
        "invoice_amount": "8750.00",
        "currency": "USD",
        "line_items": [
            {"description": "Line haul", "amount": "8300.00"},
            {"description": "Fuel surcharge", "amount": "450.00"},
        ],
        "charges": [
            "The base transportation service, identified as line haul, totals 8300.00",
            "The carrier applied a fuel surcharge totaling 450.00",
        ],
    },
]


def cases():
    """Return varied invoice/email pairs with identical supported field contracts."""
    for case in CASES:
        header = [
            f"Invoice: {case['invoice_number']}",
            f"PO: {case['po_number']}",
            f"Remit to: {case['vendor_name']}",
        ]
        if int(case["id"].rsplit("-", 1)[1]) % 2:
            header.reverse()
        invoice = "\n".join([
            "Northline Freight Brokerage | Carrier billing statement",
            *header,
            "Charges described below are payable under the referenced purchase order.",
            *case["charges"],
            f"Total due: {case['currency']} {case['invoice_amount']}",
        ])
        email = (f"Please review {case['invoice_number']} against {case['po_number']}. "
                 "The invoice narrative describes the charges; the attached statement contains the total.")
        gold = {key: case[key] for key in
                ("po_number", "vendor_name", "invoice_number", "invoice_amount", "currency", "line_items")}
        yield {"id": case["id"], "invoice": invoice, "email": email, "gold": gold}