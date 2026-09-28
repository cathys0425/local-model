"""Run every run_mvp fixture through the local LoRA adapter (MLX) and score it."""
import io, json, sys, time
from contextlib import redirect_stdout
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "part2"), str(ROOT / "finetuning")]
import agent, run_mvp
from mlx_client import MLXClient

client = MLXClient(ROOT / "finetuning/models/LFM2.5-2.6B-MLX/4bit", ROOT / "finetuning/adapters/invoice")
rows = []
for name, spec in run_mvp.CASES.items():
    email = spec["email"].read_text() if "email" in spec else ""
    start = time.monotonic()
    packet = agent.resolve_invoice(spec["file"].read_text(), client=client, email_text=email,
                                   injection_screen=spec.get("injection_screen", True), extractor="lfm")
    with redirect_stdout(io.StringIO()) as out:
        ok = run_mvp.evaluate(name, packet, spec)
    d = packet["disposition"]
    row = {"case": name, "pass": ok, "route": f"{d['exception_type']}/{d['recommended_action']}",
           "status": packet["status"], "extract": packet["extract_trace"].get("status"),
           "attempts": packet["extract_trace"].get("attempts"),
           "errors": packet["extract_trace"].get("validation_errors"),
           "invoice_amount": packet["extraction"].get("invoice_amount"),
           "vendor": packet["extraction"].get("vendor_name"),
           "notes": packet["extraction"].get("notes"),
           "seconds": round(time.monotonic() - start, 1)}
    rows.append(row)
    print(json.dumps(row), flush=True)
print(f"PASSED {sum(r['pass'] for r in rows)}/{len(rows)}")
Path(sys.argv[1]).write_text(json.dumps(rows, indent=2) + "\n")
