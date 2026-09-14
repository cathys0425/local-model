# Local invoice exception resolution

Part 2 of the Liquid AI Solutions Architect take-home: a bounded workflow on **LFM2.5-2.6B** that prepares invoice-exception decisions for a fictional mid-market freight broker, Northline Freight Brokerage.

The workflow accepts an invoice document and optional vendor email, extracts candidate facts locally, checks them against the source and mock business records, and produces a packet a human can review. Python owns the lookups, arithmetic, policy and routing. The model has no payment or email-send capability.

```text
TXT / PDF / image / EML
  → local document parsing or OCR
  → LFM candidate extraction
  → source validation
  → mock PO, vendor and payment lookups
  → Decimal reconciliation and policy
  → human review packet, email draft and local audit
```

## Where to start

This README is for someone reviewing or running the repository. [PRESENTATION_CONTENT.md](PRESENTATION_CONTENT.md) contains the customer story, assumptions, Liquid rationale, one-page architecture, full validation results, failure history and next steps, following the six “Bring to the session” requirements. It also contains the consolidated multi-format guidance and results.

For a quick review, run the PDF example below, inspect its source and packet, then read [agent.py](part2/agent.py) and [validation.py](part2/validation.py). For the evidence behind the claims, inspect the saved [paired benchmark](review/multiformat-paired.json) and [test output](review/multiformat-tests.log).

`part1/tool_test.py` is a separate earlier tool-calling experiment. It is not required to run Part 2. Files in `review/` document recorded executions and historical investigations; some older probes target the pre-fix API. Use the current tests and commands below for verification.

## Prerequisites

Run commands from the repository root, in Cursor's integrated terminal or any terminal.

| Component | Needed for |
|---|---|
| Python 3.11, as used in the recorded runs | Application, offline tests and evaluation |
| Local `llama-server` and an LFM2.5-2.6B GGUF | Live LFM extraction and optional brief generation |
| macOS with Command Line Tools | Compiling and running the Apple Vision OCR helper for images/scans |
| Poppler's `pdftoppm` on `PATH`, or `POPPLER_BIN` configured | Scanned-PDF rasterization and fixture generation |
| ReportLab from the development requirements | Regenerating the synthetic corpus only |

The model weights, server executable, OCR binary and Poppler are not bundled in the repository. Native text PDFs and TXT files do not require the OCR helper or Poppler. The current image/scan path uses macOS Vision; a Linux/Windows OCR adapter is not implemented.

### Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r part2/requirements.txt
```

The runtime requirements pin `openai==3.13.0` and `pypdf==6.10.0`. The OpenAI SDK is an API client for the local server. No cloud API key is required, and the normal resolver has no cloud fallback.

### Start the local model

Use your actual GGUF path in a separate terminal:

```bash
llama-server -m /absolute/path/to/LFM2.5-2.6B.gguf \
  --alias lfm2.5-2.6b --host 127.0.0.1 --port 8080 --jinja
```

Check that the server is ready and advertises the expected alias:

```bash
curl --max-time 5 http://127.0.0.1:8080/health
curl --max-time 5 http://127.0.0.1:8080/v1/models
```

`agent.py` uses `http://127.0.0.1:8080/v1` and model alias `lfm2.5-2.6b`. Each request has a 120-second timeout and no automatic transport retries. Invalid extraction gets at most one validation repair; a transport failure produces a review packet. Optional brief generation adds another request. These are request bounds, not a 120-second end-to-end guarantee.

## Run the first example

With the server running and the virtual environment active:

```bash
python part2/run_mvp.py \
  --invoice part2/artifacts/multiformat/overcharge.pdf --no-brief
```

This native text PDF needs no OCR setup. Open the invoice beside the output: ABC Logistics requests **$12,450** against a **$12,000** PO. Its two charges add up, but the **$450** difference exceeds the mock **$100** tolerance.

Expected important output:

```text
Status:       HUMAN_APPROVAL_REQUIRED
Exception:    amount_mismatch
Action:       short_pay
Auto-post:    False
Audit:        written
```

Also inspect `Extraction trace` for `status: ok`, the extracted invoice ID `INV-7201`, total `12450.00`, PO `PO-4821`, and mismatch `amount_delta: 450.00`. A plausible action alone is not evidence of correct extraction. The proposal is to pay the PO amount **pending human approval and variance backup**; it does not establish that the fuel surcharge is contractually invalid.

`--no-brief` uses a deterministic clerk brief while retaining LFM extraction. Omit it to request optional LFM composition from approved sentences. The generated brief is constrained; invalid prose is replaced with the template and a visible fallback trace.

The original invoice plus separate vendor-email example is also available:

```bash
python part2/run_mvp.py --invoice part2/artifacts/invoice_001.txt \
  --email part2/artifacts/vendor_email_001.txt
```

## Run images, scanned PDFs and email attachments

Compile the local OCR helper once on macOS:

```bash
mkdir -p part2/.bin
clang -fno-modules -framework Foundation -framework Vision -framework CoreGraphics \
  part2/ocr.m -o part2/.bin/local-ocr
```

For scanned PDFs, make `pdftoppm` available on `PATH`. If Poppler is installed elsewhere, set its bin directory for the terminal running the demo:

```bash
export POPPLER_BIN=/absolute/path/to/poppler/bin
```

These paths are examples to replace with your installation paths. No developer-specific Codex installation is required.

```bash
python part2/run_mvp.py --invoice part2/artifacts/multiformat/matched.png --no-brief
python part2/run_mvp.py --invoice part2/artifacts/multiformat/unknown_scan.pdf --no-brief
python part2/run_mvp.py --invoice part2/artifacts/multiformat/wrong_vendor.eml --no-brief
python part2/run_mvp.py --invoice part2/artifacts/multiformat/injection.eml --no-brief
```

| File | Expected exception / action |
|---|---|
| `matched.png` | `matched / approve_match` |
| `unknown_scan.pdf` | `unknown_po / request_information` |
| `wrong_vendor.eml` | `vendor_mismatch / escalate` |
| `injection.eml` | `prompt_injection / escalate`; extraction intentionally skipped |

The EML examples contain one native PDF attachment and a plain-text email body. Passing the EML as `--invoice` reads both. A separate `--email` must accompany `--invoice`; an EML used as a companion email must not contain attachments. Email context can reveal conflicts but cannot replace invoice facts or authorize payment.

To try an unseen document, pass its path to `--invoice`. Unsupported or ambiguous inputs should produce a review outcome; success is not guaranteed merely because the extension is supported.

## Output and approval contract

| Status | Meaning |
|---|---|
| `HUMAN_APPROVAL_REQUIRED` | A checked match or overbilling proposal is ready for a human decision |
| `HUMAN_REVIEW_REQUIRED` | Missing/conflicting facts, policy concerns, suspicious content or operational failure need review |

`approve_match` is a recommendation. `Human: approve, edit, escalate` lists intended choices; the CLI does not capture an approval event. `auto_post` remains false. The displayed `confidence` is a policy label, not a calibrated probability.

Each resolution attempts to append a full packet to `part2/audit/packets.jsonl`. Packets include a UUID, UTC timestamp, fields/evidence, backend records, mismatch calculations, disposition, draft and traces. Successful custom-file ingestion adds source hashes, converted text and page/OCR details. Audit-write failure changes the returned outcome to review-required. The local JSONL file is not a production-grade tamper-proof audit store; its contents include document text.

CLI exit codes are `1` for fixture-evaluation failure, `2` for custom-input operational failures, and `0` for a produced business proposal/review outcome. Always inspect the packet: exit `0` does not mean payment approval or successful extraction of every document.

## Verify behavior and inspect the evidence

Offline regression tests do not need a model server, OCR binary or Poppler; OCR/failure paths use controlled responses and checked-in native PDF/email fixtures:

```bash
python -m unittest discover -s part2 -p 'test_*.py' -v
```

Run the original five text fixtures against the real local model:

```bash
python part2/run_mvp.py --case all --no-brief
```

The multi-format benchmark shares conversion, source validation, mock records, policy and a template brief between candidates. It measures five critical fields, exact routing, proposal errors and pipeline time. Use new output filenames to preserve the recorded evidence:

```bash
# Complete corpus; no language-model server needed, but OCR/Poppler are required.
python part2/benchmark.py --methods rules --output review/rerun-multiformat-rules.json

# Four different cases spanning PDF, PNG, scanned PDF and EML.
python part2/benchmark.py --methods rules lfm --limit 4 \
  --output review/rerun-multiformat-paired.json
```

Remove `--limit 4` for a full paired run, budgeting for variable model latency. Appendix A of [PRESENTATION_CONTENT.md](PRESENTATION_CONTENT.md) documents the opt-in larger-model comparison. It requires an already-running local model; no larger model has been evaluated in the recorded results.

| Recorded check | Result |
|---|---|
| Offline suite | 52 tests passed |
| Complete rules corpus | 24/24 routes; all five fields exact on 20/20 eligible files |
| Paired rules / LFM smoke set | Both 4/4 routes and five-field agreement |
| Paired median pipeline time | Rules 0.973 seconds; LFM 48.591 seconds |

The four injection variants intentionally skip extraction, explaining the 20-file field denominator. The corpus has **24 files but six business scenarios and three related template variants**. It contains clean synthetic rasters, not real camera photos or degraded scans. These results demonstrate integration and known-case behavior. They do not establish broad accuracy, production ROI, a latency SLA, or superiority over rules. The full rules evaluation overlapped part of the paired run; timing was not an isolated hardware experiment.

Recorded evidence: [paired report](review/multiformat-paired.json), [full rules report](review/multiformat-rules.json), [offline test output](review/multiformat-tests.log), [email-attachment injection output](review/multiformat-cli-injection.log). The presentation explains the method, limitations and implications for model necessity.

## Economics and fixture reproduction

The ROI calculator reports an explicitly assumed capacity scenario, not observed savings:

```bash
python part2/roi.py --monthly-cost 1000 --setup-cost 10000
```

Its defaults yield 150 hours/month freed and $59,000 first-year net capacity value under the stated labor, coverage and cost assumptions. See Section 1 of the presentation for the calculation and sensitivity. [pilot_measurements.csv](part2/pilot_measurements.csv) is an empty template for collecting actual pilot data.

To regenerate fixtures, install the development dependencies and ensure Poppler is available:

```bash
python -m pip install -r part2/requirements-dev.txt
python part2/create_corpus.py
```

This rewrites the generated documents and [manifest](part2/artifacts/multiformat/manifest.json). Preserve the existing corpus when reproducing saved reports: the benchmark verifies document hashes, and regenerated MIME files can have different bytes. Do not treat old results as measurements of a changed corpus.

## Source-code reading guide

| File | Responsibility |
|---|---|
| [run_mvp.py](part2/run_mvp.py) | CLI, packet display and original fixture evaluation |
| [ingestion.py](part2/ingestion.py), [ocr.m](part2/ocr.m) | Local MIME/PDF/OCR conversion, provenance and ingestion holds |
| [agent.py](part2/agent.py) | Model calls, bounded repair, mandatory orchestration, policy routing, brief constraints and audit |
| [validation.py](part2/validation.py) | Candidate types, source support, recognizable conflicts and printed-item completeness |
| [backends.py](part2/backends.py) | Mock PO/vendor/payment data, Decimal reconciliation and deterministic email drafts |
| [test_agent.py](part2/test_agent.py), [test_ingestion.py](part2/test_ingestion.py) | Regression and controlled failure checks |
| [benchmark.py](part2/benchmark.py) | Generic rules extractor and paired evaluation using shared checks |
| [create_corpus.py](part2/create_corpus.py) | Synthetic document layouts, labels and manifest generation |
| [roi.py](part2/roi.py) | Parameterized capacity economics with explicit operating/setup costs |

LFM emits the `submit_extracted_fields` tool call. Host Python then calls the mock PO/vendor/payment functions, computes mismatches and drafts the email. This is fixed orchestration with mandatory checks, not a model choosing arbitrary backend tools.

## Supported boundaries and troubleshooting

The financial contract supports USD policies, nonnegative cent amounts, labeled payees/totals, `PO-<digits>` and `INV-<alphanumeric>` references. It checks printed charges against the invoice total and the aggregate PO; full PO-line allocation, credits, tax inference and FX are not implemented. The $100 tolerance and short-pay action are mock customer policies.

Ingestion limits are 10 MiB per document, five pages per PDF and 24,000 combined text characters. Encrypted PDFs, HTML-only email and multiple attachments are held. PDFs containing both native text and images are conservatively held even if they merely contain a logo. OCR confidence below 0.8 triggers review, but that threshold is uncalibrated: high confidence can still accompany incorrect or omitted text.

| Symptom | What to check |
|---|---|
| Health check fails or packet reports `extraction_failure` | Server readiness, local endpoint, correct alias, tool-call/finish trace and validation errors |
| Missing OCR helper | Run the `clang` command above on macOS; the generated binary is ignored by Git |
| `pdftoppm` missing or rasterization fails | Poppler installation, executable path and `POPPLER_BIN` in the current terminal |
| `ingestion_review` on a readable document | OCR confidence or mixed PDF layers may require visual source review |
| `input_failure` | Extension, permissions, file/page limits, encryption, MIME body or attachment ambiguity |
| `audit_failure` | Write access to `part2/audit/`; inspect the returned error before trusting persistence |
| Slow run | Review trace timings; `--no-brief` skips optional composition, not extraction. Do not infer a total deadline from the per-request timeout |

Source evidence checks converted text, not document authenticity or OCR fidelity against pixels. Known injection phrases are screened before model/backend calls, but phrase matching is not a universal defense. The central controls are constrained outputs, mandatory source/business checks, restricted capabilities and human authority.
