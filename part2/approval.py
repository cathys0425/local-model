#!/usr/bin/env python3
"""Record a reviewer's decision on an audited packet. Nothing is posted to payment."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent

DECISIONS = ("approve", "reject", "escalate")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def find_packet(packet_id: str, audit_dir: Path | None = None) -> dict[str, Any] | None:
    for row in _read_jsonl((audit_dir or agent.AUDIT_DIR) / "packets.jsonl"):
        if row.get("packet", {}).get("packet_id") == packet_id:
            return row["packet"]
    return None


def proposed_amount(packet: dict[str, Any]) -> str | None:
    """The amount a reviewer approves comes from the packet, never from the reviewer."""
    action = packet["disposition"]["recommended_action"]
    if action == "short_pay":
        return packet["mismatch"].get("po_amount")
    if action == "approve_match":
        return packet["mismatch"].get("invoice_amount")
    return None


def record_decision(packet_id: str, decision: str, reviewer: str, note: str = "",
                    audit_dir: Path | None = None) -> dict[str, Any]:
    audit_dir = audit_dir or agent.AUDIT_DIR
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    if not reviewer.strip():
        raise ValueError("reviewer name is required")
    packet = find_packet(packet_id, audit_dir)
    if packet is None:
        raise ValueError(f"no audited packet {packet_id}; unaudited packets cannot be decided")
    if decision not in packet["human_decision"]:
        raise ValueError(f"{decision} is not available for a {packet['status']} packet; "
                         f"options: {', '.join(packet['human_decision'])}")
    decisions = audit_dir / "decisions.jsonl"
    if any(row.get("packet_id") == packet_id for row in _read_jsonl(decisions)):
        raise ValueError(f"packet {packet_id} already has a recorded decision")
    record = {
        "packet_id": packet_id,
        "decision": decision,
        "reviewer": reviewer.strip(),
        "note": note,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "invoice_number": packet["extraction"].get("invoice_number"),
        "recommended_action": packet["disposition"]["recommended_action"],
        "approved_amount_usd": proposed_amount(packet) if decision == "approve" else None,
        "vendor_id": (packet["lookups"].get("vendor") or {}).get("vendor_id") if decision == "approve" else None,
        # Posting belongs to the ERP's payment run, outside this demo.
        "payment_posted": False,
    }
    audit_dir.mkdir(exist_ok=True)
    with decisions.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, allow_nan=False) + "\n")
    return record


def prompt_for_decision(packet: dict[str, Any], ask=input) -> dict[str, Any] | None:
    """Interactive gate used by the demo CLIs."""
    if packet.get("audit_status") != "written":
        print("\nDecision not recorded: the packet has no audit record.")
        return None
    options = packet["human_decision"]
    answer = ask(f"\nReviewer decision [{'/'.join(options)}/skip]: ").strip().lower()
    if answer in ("", "skip"):
        print("No decision recorded; the packet stays in the queue.")
        return None
    reviewer = ask("Reviewer name: ")
    note = ask("Note (optional): ")
    try:
        record = record_decision(packet["packet_id"], answer, reviewer, note)
    except ValueError as exc:
        print(f"Decision not recorded: {exc}")
        return None
    amount = record["approved_amount_usd"]
    print(f"Recorded: {record['decision']} by {record['reviewer']}"
          + (f" for {amount} USD to vendor {record['vendor_id']}" if amount else "")
          + "; payment posted: no.")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_id")
    parser.add_argument("decision", choices=DECISIONS)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    try:
        record = record_decision(args.packet_id, args.decision, args.reviewer, args.note)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
