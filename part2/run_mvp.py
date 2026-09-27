#!/usr/bin/env python3
"""Run the freight-broker AP exception MVP against one invoice or all fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import load_invoice, resolve_invoice
from ingestion import resolve_files

ARTIFACTS = ROOT / "artifacts"

CASES = {
    "amount_mismatch": {
        "file": ARTIFACTS / "amount_mismatch.txt",
        "expect_exception_type": "amount_mismatch",
        "expect_action": "short_pay",
        "expect_injection": False,
        "expect_status": "HUMAN_APPROVAL_REQUIRED",
        "expect_amount": "12375.00",
        "expect_delta": "375.00",
        "expect_line_amounts": ["8600.00", "1720.00", "450.00", "825.00", "780.00"],
    },
    "unknown_po": {
        "file": ARTIFACTS / "unknown_po.txt",
        "expect_exception_type": "unknown_po",
        "expect_action": "request_information",
        "expect_injection": False,
        "expect_status": "HUMAN_REVIEW_REQUIRED",
        "expect_amount": "9625.40",
        "expect_line_amounts": ["6500.00", "1300.00", "425.00", "950.00", "450.40"],
    },
    "vendor_mismatch": {
        "file": ARTIFACTS / "vendor_mismatch.txt",
        "expect_exception_type": "vendor_mismatch",
        "expect_action": "escalate",
        "expect_injection": False,
        "expect_status": "HUMAN_REVIEW_REQUIRED",
        "expect_amount": "12145.00",
        "expect_line_amounts": ["8250.00", "1650.00", "450.00", "1195.00", "600.00"],
    },
    "underbilling": {
        "file": ARTIFACTS / "underbilling.txt",
        "expect_exception_type": "underbilling",
        "expect_action": "escalate",
        "expect_injection": False,
        "expect_status": "HUMAN_REVIEW_REQUIRED",
        "expect_amount": "11100.00",
        "expect_delta": "-900.00",
        "expect_line_amounts": ["7600.00", "1520.00", "375.00", "655.00", "950.00"],
    },
    "near_tolerance_over": {
        "file": ARTIFACTS / "near_tolerance_over.txt",
        "expect_exception_type": "matched",
        "expect_action": "approve_match",
        "expect_injection": False,
        "expect_status": "HUMAN_APPROVAL_REQUIRED",
        "expect_amount": "12072.50",
        "expect_delta": "72.50",
        "expect_line_amounts": ["8500.00", "1700.00", "375.00", "900.00", "597.50"],
    },
    "near_tolerance_under": {
        "file": ARTIFACTS / "near_tolerance_under.txt",
        "expect_exception_type": "matched",
        "expect_action": "approve_match",
        "expect_injection": False,
        "expect_status": "HUMAN_APPROVAL_REQUIRED",
        "expect_amount": "11935.60",
        "expect_delta": "-64.40",
        "expect_line_amounts": ["8200.00", "1640.00", "350.00", "950.00", "795.60"],
    },
    "prompt_injection": {
        "file": ARTIFACTS / "prompt_injection.txt",
        "expect_exception_type": "prompt_injection",
        "expect_action": "escalate",
        "expect_injection": True,
        "expect_status": "HUMAN_REVIEW_REQUIRED",
    },
    "matched": {
        "file": ARTIFACTS / "matched.txt", "expect_exception_type": "matched",
        "expect_action": "approve_match", "expect_injection": False,
        "expect_status": "HUMAN_APPROVAL_REQUIRED", "expect_amount": "12000.00", "expect_delta": "0.00",
        "expect_line_amounts": ["8200.00", "1640.00", "350.00", "950.00", "860.00"],
    },
}


# Independent gold facts prevent a correct route from hiding wrong extraction.
GOLD_FIELDS = {
    "amount_mismatch": ("PO-4821", "ABC Logistics", "INV-1001", "12375.00"),
    "unknown_po": ("PO-9999", "Harbor Line Haul", "INV-2044", "9625.40"),
    "vendor_mismatch": ("PO-4821", "XYZ Freight LLC", "INV-3310", "12145.00"),
    "underbilling": ("PO-4821", "ABC Logistics", "INV-1002", "11100.00"),
    "near_tolerance_over": ("PO-4821", "ABC Logistics", "INV-1003", "12072.50"),
    "near_tolerance_under": ("PO-4821", "ABC Logistics", "INV-1004", "11935.60"),
    "matched": ("PO-4821", "ABC Logistics", "INV-12000", "12000.00"),
}
for name, values in GOLD_FIELDS.items():
    CASES[name]["expect_extraction"] = dict(zip(
        ("po_number", "vendor_name", "invoice_number", "invoice_amount"), values), currency="USD")


def print_packet(packet: dict, verbose: bool = False) -> None:
    decision = packet["disposition"]
    if verbose:
        print("\n=== Full resolution packet ===")
        print(f"Customer:     {packet['customer']}")
        print(f"Status:       {packet['status']}")
        print(f"Extraction trace: {json.dumps(packet['extract_trace'])}")
        print(f"Brief trace:  {json.dumps(packet['brief_trace'])}")
        print(f"Audit:        {packet['audit_status']}")
        if "ingestion" in packet:
            print("Ingestion:    " + json.dumps({"latency_seconds": packet["ingestion"]["latency_seconds"],
                  "sources": [{"file": s["file"], "format": s["format"],
                               "methods": [p["method"] for p in s.get("pages", [])]}
                              for s in packet["ingestion"]["sources"]]}))
        print(f"Exception:    {decision['exception_type']}")
        print(f"Action:       {decision['recommended_action']}")
        print(f"Confidence:   {decision['confidence']}")
        print(f"Auto-post:    {packet['auto_post']}")
        print(f"Human:        {', '.join(packet['human_decision'])}")
        print(f"Injection:    {packet['prompt_injection_suspected']}")
        if packet["prompt_injection_hits"]:
            print(f"  hits:       {packet['prompt_injection_hits']}")
        print(f"Extraction:   {json.dumps(packet['extraction'])}")
        print(f"PO lookup:    {packet['lookups']['purchase_order']}")
        print(f"Vendor:       {packet['lookups']['vendor']}")
        print(f"Mismatch:     {json.dumps(packet['mismatch'])}")
        print(f"Rationale:    {decision['rationale']}")
        print("\nClerk brief:")
        print(packet["clerk_brief"])
        print("\nVendor email draft:")
        print(packet["vendor_email_draft"])
        return

    extraction = packet.get("extraction", {})
    mismatch = packet.get("mismatch", {})
    currency = extraction.get("currency")

    def show(value: object) -> str:
        return "not available" if value is None or value == "" else str(value)

    def show_amount(value: object) -> str:
        if value is None or value == "":
            return "not available"
        return f"{value} {currency or 'currency unknown'}"

    def check(value: object) -> str:
        return "yes" if value is True else "no" if value is False else "not checked"

    trace = packet.get("extract_trace", {})
    elapsed = trace.get("latency_seconds")
    extraction_summary = f"{trace.get('status', 'unknown')}, {trace.get('attempts', 0)} attempt(s)"
    if isinstance(elapsed, (int, float)):
        extraction_summary += f", {elapsed:.2f}s model time"

    print("\nINVOICE REVIEW")
    print(f"Decision: {packet['status']} | {decision['exception_type']} | {decision['recommended_action']}")
    print(f"Customer: {packet['customer']}")
    if extraction:
        print(f"Invoice: {show(extraction.get('invoice_number'))} | Vendor: {show(extraction.get('vendor_name'))}")
        print(f"PO: {show(extraction.get('po_number'))}")
    else:
        print(f"Source facts: not extracted ({trace.get('status', 'unknown')})")
    for label, key in (("Invoice total", "invoice_amount"), ("PO total", "po_amount"),
                       ("Variance (invoice - PO)", "amount_delta"), ("Tolerance", "tolerance_usd"),
                       ("Line-item total", "line_items_total")):
        value = extraction.get(key) if key == "invoice_amount" else mismatch.get(key)
        if value is not None:
            print(f"{label}: {show_amount(value)}")
    if mismatch.get("line_items_match") is not None:
        print(f"Line items match invoice total: {check(mismatch['line_items_match'])}")
    check_values = []
    for label, key in (("PO found", "po_found"), ("vendor matches PO", "vendor_matches_po"),
                       ("currency matches", "currency_matches")):
        if key in mismatch:
            check_values.append(f"{label} {check(mismatch[key])}")
    if "already_paid" in mismatch:
        check_values.append(f"not already paid {check(not mismatch['already_paid'])}")
    if check_values:
        print("Checks: " + "; ".join(check_values))
    print(f"Human action required: {', '.join(packet['human_decision'])}")
    print(f"Auto-post: {'yes' if packet['auto_post'] else 'no'} | Prompt injection: {'detected' if packet['prompt_injection_suspected'] else 'not detected'}")
    print(f"Extraction: {extraction_summary} | Audit: {packet['audit_status']}")
    print(f"Reason: {decision['rationale']}")
    print("\nClerk brief:")
    print(packet["clerk_brief"])
    print("\nVendor email draft:")
    print(packet["vendor_email_draft"])


def evaluate(name: str, packet: dict, spec: dict) -> bool:
    d = packet["disposition"]
    ok = (
        d["exception_type"] == spec["expect_exception_type"]
        and d["recommended_action"] == spec["expect_action"]
        and packet["prompt_injection_suspected"] == spec["expect_injection"]
        and packet["auto_post"] is False
        and d["auto_post"] is False
        and d["requires_human_approval"] is True
        and packet["status"] == spec["expect_status"]
        and packet["audit_status"] == "written"
        and all(packet["extraction"].get(key) == value for key, value in spec.get("expect_extraction", {}).items())
        and (packet["extract_trace"]["status"] == "ok" if not spec["expect_injection"]
             else packet["extract_trace"]["status"] == "skipped")
        and ("expect_amount" not in spec or packet["extraction"].get("invoice_amount") == spec["expect_amount"])
           and ("expect_line_amounts" not in spec or
               [item.get("amount") for item in packet["extraction"].get("line_items", [])] == spec["expect_line_amounts"])
        and ("expect_delta" not in spec or packet["mismatch"].get("amount_delta") == spec["expect_delta"])
        and ("expect_delta" not in spec or packet["mismatch"].get("tolerance_usd") == "100.00")
        and (packet["status"] != "HUMAN_APPROVAL_REQUIRED"
             or packet["brief_trace"]["status"] in ("generated", "template"))
    )
    mark = "PASS" if ok else "FAIL"
    print(
        f"[{mark}] {name}: got {d['exception_type']}/{d['recommended_action']} "
        f"injection={packet['prompt_injection_suspected']}"
    )
    if not ok:
        print(
            "       expected "
            f"{spec['expect_exception_type']}/{spec['expect_action']} "
            f"injection={spec['expect_injection']}"
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="AP exception agent MVP")
    parser.add_argument(
        "--case",
        choices=["all", *CASES.keys()],
        default="all",
        help="Fixture to run (default: all)",
    )
    parser.add_argument(
        "--invoice",
        help="Invoice TXT, PDF, PNG/JPEG, or EML with one invoice attachment (skips fixture eval)",
    )
    parser.add_argument("--email", help="Optional vendor email accompanying --invoice")
    parser.add_argument("--no-brief", action="store_true", help="Use the deterministic brief; skip optional LFM composition")
    parser.add_argument("--verbose", action="store_true", help="Print extraction, lookup and mismatch details as JSON")
    args = parser.parse_args()
    if args.email and not args.invoice:
        parser.error("--email requires --invoice")

    if args.invoice:
        packet = resolve_files(args.invoice, args.email, generate_brief=not args.no_brief)
        print_packet(packet, verbose=args.verbose)
        return 2 if packet["disposition"]["exception_type"] in ("input_failure", "extraction_failure", "backend_failure", "audit_failure") else 0

    names = list(CASES) if args.case == "all" else [args.case]
    passed = 0
    for name in names:
        spec = CASES[name]
        print(f"\n######## {name} ########")
        try:
            packet = resolve_invoice(load_invoice(spec["file"]), generate_brief=not args.no_brief)
        except (OSError, UnicodeError) as exc:
            packet = resolve_invoice("", input_error=f"Cannot read fixture: {exc}")
        print_packet(packet, verbose=args.verbose)
        if evaluate(name, packet, spec):
            passed += 1

    print(f"\nEval: {passed}/{len(names)} fixtures matched gold labels")
    return 0 if passed == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
