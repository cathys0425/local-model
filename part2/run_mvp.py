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

ARTIFACTS = ROOT / "artifacts"

CASES = {
    "amount_mismatch": {
        "file": ARTIFACTS / "amount_mismatch.txt",
        "expect_exception_type": "amount_mismatch",
        "expect_action": "short_pay",
        "expect_injection": False,
    },
    "unknown_po": {
        "file": ARTIFACTS / "unknown_po.txt",
        "expect_exception_type": "unknown_po",
        "expect_action": "request_information",
        "expect_injection": False,
    },
    "vendor_mismatch": {
        "file": ARTIFACTS / "vendor_mismatch.txt",
        "expect_exception_type": "vendor_mismatch",
        "expect_action": "escalate",
        "expect_injection": False,
    },
    "prompt_injection": {
        "file": ARTIFACTS / "prompt_injection.txt",
        "expect_exception_type": "prompt_injection",
        "expect_action": "escalate",
        "expect_injection": True,
    },
}


def print_packet(packet: dict) -> None:
    d = packet["disposition"]
    print("\n=== Resolution packet (human approval required) ===")
    print(f"Customer:     {packet['customer']}")
    print(f"Exception:    {d['exception_type']}")
    print(f"Action:       {d['recommended_action']}")
    print(f"Confidence:   {d['confidence']}")
    print(f"Auto-post:    {packet['auto_post']}")
    print(f"Human:        {', '.join(packet['human_decision'])}")
    print(f"Injection:    {packet['prompt_injection_suspected']}")
    if packet["prompt_injection_hits"]:
        print(f"  hits:       {packet['prompt_injection_hits']}")
    print(f"Extraction:   {json.dumps(packet['extraction'])}")
    print(f"PO lookup:    {packet['lookups']['purchase_order']}")
    print(f"Vendor:       {packet['lookups']['vendor']}")
    print(f"Mismatch:     {json.dumps(packet['mismatch'])}")
    print(f"Rationale:    {d['rationale']}")
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
        help="Path to a raw invoice text file (skips fixture eval)",
    )
    args = parser.parse_args()

    if args.invoice:
        packet = resolve_invoice(load_invoice(args.invoice))
        print_packet(packet)
        return 0

    names = list(CASES) if args.case == "all" else [args.case]
    passed = 0
    for name in names:
        spec = CASES[name]
        print(f"\n######## {name} ########")
        packet = resolve_invoice(load_invoice(spec["file"]))
        print_packet(packet)
        if evaluate(name, packet, spec):
            passed += 1

    print(f"\nEval: {passed}/{len(names)} fixtures matched gold labels")
    return 0 if passed == len(names) else 1


if __name__ == "__main__":
    raise SystemExit(main())
