"""Paired synthetic comparison of rules, base LFM, and LoRA on language variation."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "part2"))

import agent
from backends import compute_mismatch, lookup_purchase_order, lookup_vendor, money
from rules import rules_extract
from language_cases import cases
from validation import FIELDS, validate_extraction
from mlx_client import MLXClient


def extraction_exact(actual, gold):
    try:
        fields_exact = all(
            money(actual[key]) == money(gold[key]) if key == "invoice_amount"
            else actual[key] == gold[key]
            for key in FIELDS
        )
        actual_items = actual["line_items"]
        expected_items = gold["line_items"]
        items_exact = len(actual_items) == len(expected_items)
        if items_exact:
            unmatched = list(expected_items)
            for actual_item in actual_items:
                concept = charge_concept(actual_item["description"])
                match = next((item for item in unmatched
                              if charge_concept(item["description"]) == concept
                              and money(item["amount"]) == money(actual_item["amount"])), None)
                if match is None:
                    items_exact = False
                    break
                unmatched.remove(match)
        return fields_exact, items_exact, fields_exact and items_exact
    except (KeyError, TypeError, ValueError):
        return False, False, False


def charge_concept(description):
    words = re.findall(r"[a-z]+", description.casefold().replace("linehaul", "line haul"))
    if "fuel" in words and "surcharge" in words:
        return "fuel surcharge"
    if "line" in words and "haul" in words:
        return "line haul"
    return "unknown"


def expected_route(gold):
    po = lookup_purchase_order(gold["po_number"])
    vendor = lookup_vendor(gold["vendor_name"])
    mismatch = compute_mismatch(gold, po, vendor)
    decision = agent.decide_disposition(gold, po, vendor, mismatch, [])
    return decision["exception_type"], decision["recommended_action"]


def candidate_route(fields):
    po = lookup_purchase_order(fields["po_number"])
    vendor = lookup_vendor(fields["vendor_name"])
    mismatch = compute_mismatch(fields, po, vendor)
    decision = agent.decide_disposition(fields, po, vendor, mismatch, [])
    return decision["status"], decision["exception_type"], decision["recommended_action"]


def run_extraction(method, case, client):
    if method == "rules":
        fields, trace = rules_extract(None, case["invoice"], case["email"])
        return fields, trace
    response = client.create(
        messages=agent.extraction_messages(case["invoice"], case["email"]),
        tools=[agent.EXTRACT_TOOL],
    )
    choice = response.choices[0]
    if choice.finish_reason == "length" or not choice.message.tool_calls:
        raise ValueError("model did not return a complete extraction tool call")
    fields = json.loads(choice.message.tool_calls[0].function.arguments)
    return fields, client.last


def score(method, case, client):
    started = time.monotonic()
    row = {"id": case["id"], "method": method}
    try:
        fields, trace = run_extraction(method, case, client)
        fields_exact, line_items_exact, all_exact = extraction_exact(fields, case["gold"])
        errors = validate_extraction(fields, case["invoice"], case["email"])
        row.update(
            fields_exact=fields_exact,
            line_items_exact=line_items_exact,
            extraction_exact=all_exact,
            validation_errors=errors,
            validated=not errors,
            extraction_trace=trace,
        )
        if not errors:
            status, exception_type, action = candidate_route(fields)
            expected_exception, expected_action = expected_route(case["gold"])
            route_correct = (exception_type, action) == (expected_exception, expected_action)
            proposed = action in ("short_pay", "approve_match")
            row.update(
                status=status,
                exception_type=exception_type,
                recommended_action=action,
                route_correct=route_correct,
                proposal=proposed,
                incorrect_proposal=proposed and (not all_exact or not route_correct),
                human_review_required=status == "HUMAN_REVIEW_REQUIRED",
                human_approval_required=True,
            )
        else:
            row.update(
                status="HUMAN_REVIEW_REQUIRED",
                exception_type="extraction_failure",
                recommended_action="escalate",
                route_correct=False,
                proposal=False,
                incorrect_proposal=False,
                human_review_required=True,
                human_approval_required=True,
            )
    except Exception as exc:
        row.update(
            fields_exact=False,
            line_items_exact=False,
            extraction_exact=False,
            validation_errors=[f"{type(exc).__name__}: {exc}"],
            validated=False,
            status="HUMAN_REVIEW_REQUIRED",
            exception_type="extraction_failure",
            recommended_action="escalate",
            route_correct=False,
            proposal=False,
            incorrect_proposal=False,
            human_review_required=True,
            human_approval_required=True,
        )
    row["useful_coverage"] = bool(row["validated"] and row["extraction_exact"] and row["route_correct"])
    row["seconds"] = round(time.monotonic() - started, 3)
    return row


def summarize(rows):
    summaries = {}
    for method in sorted({row["method"] for row in rows}):
        subset = [row for row in rows if row["method"] == method]
        count = len(subset)
        summaries[method] = {
            "documents": count,
            "fields_exact": sum(row["fields_exact"] for row in subset),
            "line_items_exact": sum(row["line_items_exact"] for row in subset),
            "extraction_exact": sum(row["extraction_exact"] for row in subset),
            "validated": sum(row["validated"] for row in subset),
            "useful_coverage": sum(row["useful_coverage"] for row in subset),
            "route_correct": sum(row["route_correct"] for row in subset),
            "proposals": sum(row["proposal"] for row in subset),
            "incorrect_proposals": sum(row["incorrect_proposal"] for row in subset),
            "human_review_required": sum(row["human_review_required"] for row in subset),
            "human_review_rate": round(sum(row["human_review_required"] for row in subset) / count, 3),
            "human_approval_required_rate": round(sum(row["human_approval_required"] for row in subset) / count, 3),
            "median_seconds": round(statistics.median(row["seconds"] for row in subset), 3),
        }
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", nargs="+", choices=("rules", "base", "lora"),
                        default=("rules", "base", "lora"))
    parser.add_argument("--model", default=str(ROOT / "models/LFM2.5-2.6B-MLX/4bit"))
    parser.add_argument("--adapter", default=str(ROOT / "adapters/invoice"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path; recorded evidence is not overwritten")

    test_cases = list(cases())
    cases_json = json.dumps(test_cases, sort_keys=True, ensure_ascii=False).encode()
    clients = {}
    for method in args.methods:
        if method == "base":
            clients[method] = MLXClient(args.model)
        elif method == "lora":
            clients[method] = MLXClient(args.model, args.adapter)

    rows = []
    report = {
        "scope": "small synthetic language-variation probe; not customer validation",
        "platform": platform.platform(),
        "model": args.model,
        "adapter": args.adapter if "lora" in args.methods else None,
        "case_count": len(test_cases),
        "case_sha256": hashlib.sha256(cases_json).hexdigest(),
        "protocol": {
            "methods": list(args.methods),
            "same_cases_and_validation": True,
            "one_attempt": True,
            "brief": False,
            "line_item_exactness": "same canonical charge concepts and cent-exact amounts; order and extra descriptive context are ignored",
            "useful_coverage_definition": "exact five commercial fields and line items, source validation passes, and deterministic route matches gold",
            "human_review_rate_definition": "HUMAN_REVIEW_REQUIRED; all cases still require human approval and none auto-post",
        },
        "results": rows,
        "notes": [
            "Synthetic variants share two mock purchase orders and are not independent business examples.",
            "Timing is exploratory and not a controlled latency benchmark.",
            "No production accuracy, ROI, or model-superiority claim follows from this probe.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in test_cases:
        for method in args.methods:
            print(f"Running {case['id']} / {method}", flush=True)
            row = score(method, case, clients.get(method))
            rows.append(row)
            report["summary"] = summarize(rows)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print(f"  exact={row['extraction_exact']} valid={row['validated']} "
                  f"useful={row['useful_coverage']} review={row['human_review_required']}", flush=True)
    report["summary"] = summarize(rows)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()