"""Paired extraction comparison using identical ingestion, validation and policy."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import platform
import statistics
import time
from unittest.mock import patch
from urllib.parse import urlparse

import agent
from ingestion import load_inputs
from rules import rules_extract
from validation import FIELDS

ROOT = Path(__file__).resolve().parent


def summarize(rows):
    summary = {}
    for method in sorted({r["method"] for r in rows}):
        subset = [r for r in rows if r["method"] == method]
        eligible = [r for r in subset if r["gold_exception"] != "prompt_injection"]
        summary[method] = {"documents": len(subset), "case_groups": len({r["case_group"] for r in subset}),
            "five_fields_exact": sum(r["fields_exact"] for r in eligible), "field_documents": len(eligible),
            "line_item_amounts_exact": sum(r["line_items_exact"] for r in eligible),
            "line_item_documents": len(eligible),
            "route_correct": sum(r["route_correct"] for r in subset),
            "proposal_count": sum(r["proposal"] for r in subset),
            "incorrect_proposals": sum(r["proposal"] and (not r["route_correct"] or not r["fields_exact"]) for r in subset),
            "median_pipeline_seconds": round(statistics.median(r["pipeline_seconds"] for r in subset), 3),
            "field_exact_counts": {key: sum(r["field_matches"].get(key, False) for r in eligible) for key in FIELDS},
            "by_format": {fmt: {"documents": len(group), "route_correct": sum(r["route_correct"] for r in group)}
                          for fmt in sorted({r["format"] for r in subset})
                          for group in [[r for r in subset if r["format"] == fmt]]}}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", nargs="+", choices=["rules", "lfm", "larger"], default=["rules"])
    parser.add_argument("--limit", type=int, help="First N frozen manifest records; 4 is the format smoke set")
    parser.add_argument("--larger-model", help="Exact alias of a model already served locally")
    parser.add_argument("--larger-base-url", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark_results.json")
    args = parser.parse_args()
    if "larger" in args.methods and not args.larger_model:
        parser.error("--larger requires --larger-model; no model is downloaded or substituted")
    if urlparse(args.larger_base_url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Larger-model comparison must use a local loopback endpoint")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    manifest_path = ROOT / "artifacts" / "multiformat" / "manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    rows = []
    report = {"scope": manifest["scope"], "manifest_sha256": hashlib.sha256(raw).hexdigest(),
              "platform": platform.platform(), "model": agent.MODEL, "endpoint": agent.BASE_URL,
              "larger_model": args.larger_model if "larger" in args.methods else "not run",
              "larger_endpoint": args.larger_base_url if "larger" in args.methods else None,
              "brief": "deterministic for every method", "results": rows,
              "notes": "Format variants are paired replicas, not independent samples. No production ROI or superiority claim."}
    for record in manifest["records"][:args.limit]:
        path = manifest_path.parent / record["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Corpus changed after labels were frozen: {path}")
        begin = time.monotonic()
        try:
            invoice, email, ingestion = load_inputs(path)
            ingestion_error = None
        except Exception as exc:
            invoice, email, ingestion = "", "", {}
            ingestion_error = f"{type(exc).__name__}: {exc}"
        ingest_seconds = time.monotonic() - begin
        for method in args.methods:
            print(f"Running {record['id']} / {method}", flush=True)
            start = time.monotonic()
            context = patch.object(agent, "extract_fields", rules_extract) if method == "rules" else nullcontext()
            config = patch.multiple(agent, MODEL=args.larger_model, BASE_URL=args.larger_base_url) if method == "larger" else nullcontext()
            with context, config:
                packet = agent.resolve_invoice(invoice, email_text=email, ingestion=dict(ingestion, benchmark_method=method),
                                               input_error=ingestion_error)
            elapsed = time.monotonic() - start
            fields = {key: packet["extraction"].get(key) == record["gold"][key] for key in FIELDS}
            line_items_exact = ([item.get("amount") for item in packet["extraction"].get("line_items", [])]
                                == record["gold"].get("line_item_amounts", []))
            decision = packet["disposition"]
            route = (packet["status"] == record["status"] and decision["exception_type"] == record["exception"]
                     and decision["recommended_action"] == record["action"] and packet["audit_status"] == "written"
                     and packet["auto_post"] is False)
            rows.append({"id": record["id"], "case_group": record["case_group"], "format": record["format"],
                         "method": method, "gold_exception": record["exception"], "fields_exact": all(fields.values()),
                         "field_matches": fields, "line_items_exact": line_items_exact, "route_correct": route,
                         "proposal": packet["status"] == "HUMAN_APPROVAL_REQUIRED",
                         "pipeline_seconds": round(elapsed + ingest_seconds, 3), "ingestion_seconds": round(ingest_seconds, 3),
                         "processing_seconds": round(elapsed, 3), "packet": packet})
            report["summary"] = summarize(rows)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(f"  route={'PASS' if route else 'FAIL'} fields={all(fields.values())} "
                  f"{decision['exception_type']} {elapsed + ingest_seconds:.2f}s", flush=True)
    print(json.dumps(report["summary"], indent=2))
    return 0 if all(r["route_correct"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
