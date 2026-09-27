# Historical review and fix verification

This document preserves the original review and subsequent fix verification. Statements about architecture, dependencies, CLI flags, test counts and unresolved defects describe those historical snapshots, not the current implementation. For current behavior and later multi-format results, see the [README](../README.md).

## Original review: before fixes

The current project is a small, explainable local pipeline worth retaining. The six live fixture checks passed, but reliability gaps prevent treating that result as proof of correct extraction or safe recommendations. No implementation files were edited during this review. Existing user edits were preserved; running the program appended its normal audit packets.

**Scope and evidence**

Read all repository source, README, dependency declarations, eight input fixtures, and ignore rules, including the independent Part 1 experiment. Python is 3.11.2 in `.venv`; OpenAI client is 3.13.0; `pip check` reports no broken requirements. The sole declared dependency is unpinned `openai`.

The sandbox initially could not connect to localhost. An approved check outside the sandbox succeeded: `/health` returned `{"status":"ok"}` and `/v1/models` reported model ID `lfm2.5-2.6b`, owner `llamacpp`, 2,697,198,592 parameters and Q4_K Medium quantization. This verifies the server-reported identity, not a cryptographic check of model weights. All inference runs targeted `http://127.0.0.1:8080/v1`; no cloud fallback was used.

Executed:

```bash
.venv/bin/python -m pip check
.venv/bin/python part2/run_mvp.py --case all
.venv/bin/python -u part2/run_mvp.py --invoice part2/artifacts/invoice_001.txt --brief
.venv/bin/python review/probe_failures.py
.venv/bin/python -u review/trace_live.py
```

`live-fixtures.log`, `live-brief.log`, `failure-results.jsonl`, and `live-model-trace.json` contain the evidence. Fault probes use explicit mock model/backend responses; they demonstrate code behavior, not predictions of how often LFM produces those responses. Some probes isolate reconciliation by substituting extraction; the `api_*` probes exercise parsing and validation with simulated tool responses. The probe script prints observations rather than serving as a regression suite asserting desired behavior.

**Current architecture**

- Entry: `part2/run_mvp.py:163`. CLI chooses six embedded evaluation cases or a UTF-8 invoice via `--invoice`. Default is all cases; `--brief` enables optional generation. `load_invoice` reads the entire file. There is no email input argument; `vendor_email_001.txt` is unused. `invoice_001.txt` is also outside the default fixture set.
- Orchestration: `part2/agent.py:560`, `resolve_invoice`. Detect suspicious phrases, extract fields, look up PO/vendor/paid invoice, compute mismatch, decide disposition, draft email, produce brief, build packet, append JSONL audit.
- Extraction: `agent.py:391`. Local LFM gets a system instruction to copy commercial facts, treat invoice text as untrusted, distinguish carrier from broker, and never approve payment. Invoice is enclosed in `<UNTRUSTED_INVOICE>` tags. Only `submit_extracted_fields` is exposed, with `tool_choice="auto"`, 400 output tokens, and one repair attempt.
- Expected fields: `po_number`, `vendor_name`, `invoice_number`, `invoice_amount`, `currency`, `notes`. No line items or source evidence. Schema requires all keys but describes nulls without allowing null types.
- Validation: `agent.py:185`. Checks key presence, amount numeric type, and loose PO syntax/type. Coercion converts amount strings, fills missing fields using regex, and can replace a broker-name payee. JSON parsing removes fences/trailing commas, substitutes quotes, and salvages individual fields. Failure after repair can trigger regex-only extraction and continue normal routing.
- Backends: `part2/backends.py` contains three POs, three vendors with aliases and tolerance, and one paid invoice. Python calls `lookup_purchase_order`, `lookup_vendor`, and `lookup_paid_invoice`; the model does not select or execute these lookups. `draft_vendor_email` produces a string only.
- Reconciliation: `backends.py:160`. Float subtraction rounded to two decimals; absolute discrepancy compared with vendor tolerance. Currency equality is checked only when both currencies are present. Vendor matching uses broad substring/token matching plus alias records. No line-item calculation exists.
- Decision: `agent.py:219`. Precedence is injection, previously paid invoice, unknown PO, vendor mismatch, currency mismatch, missing amount, out-of-tolerance amount, matched. All branches require human approval and disable auto-post. No canonical `HUMAN_APPROVAL_REQUIRED` or `HUMAN_REVIEW_REQUIRED` status exists.
- Resolution: deterministic rationale, email draft and default clerk brief. Optional LFM brief receives extraction, mismatch and disposition JSON, including untrusted notes; any nonempty output is accepted. Empty output/errors silently fall back to template. Packet lists approve/edit/escalate options but does not capture an actual human decision. Audit appends packets without timestamps or run identifiers.
- Part 1 is a separate experiment where the model chooses a PO lookup and writes an answer. It is not called by Part 2 and need not be merged or removed.

**What actually worked in the live run**

All six existing fixture evaluations passed: amount mismatch, unknown PO, vendor mismatch, injection, vendor alias, and already paid. Five had extraction trace `ok`; injection had `fallback`, error `model did not call submit_extracted_fields`. Thus that test establishes deterministic blocking of recognized injection, not successful model compliance with the extraction prompt.

Actual example values were invoice 12450.0, PO 12000.0, delta 450.0, tolerance 1.0, action `short_pay`, exception `amount_mismatch`, human approval true, auto-post false. Arithmetic is correct. Tolerance is **$1, not the requested $100**. Human approval is required semantically, but the exact requested status string is absent. No payment or email-send operation exists or was executed.

Running the original `invoice_001.txt` with `--brief` also completed and printed the same deterministic fallback brief; it did not demonstrate successful human-readable LFM generation in that run. The traced repeat run confirmed the cause: the brief response had finish_reason `length`, 220 completion tokens, and empty final content. The token budget was exhausted before a final brief was emitted; the application silently returned its template. Extraction on that repeat succeeded. This is an observed live-generation failure, not a hypothetical risk.

**Take-home requirements**

| Requirement | Result | Evidence / limitation |
|---|---|---|
| A. Messy input | PARTIAL | Real text fixtures run successfully; email ingestion and line-item extraction absent. |
| B. Local LFM2.5-2.6B | PASS | Local server identity and live extraction verified; some runs can silently degrade to regex. |
| C. Tools/backends | PASS | Live packets contain actual deterministic mock PO/vendor/payment lookups. LFM tool call is structured extraction, not backend selection. |
| D. Deterministic validation | PARTIAL | Present but nulls, types, source consistency and required business facts are insufficiently checked. |
| E. Deterministic financial calculations | PARTIAL | $450 difference verified; underbilling routing is incorrect, tolerance differs, floats used, no line-item checks. |
| F. Human in loop | PARTIAL | Every packet requires approval and disables posting; no approval capture/state transition. Sufficient as a review handoff, not a completed approval workflow. |
| G. Safe failures | PARTIAL | Some missing data escalates; fallback can recommend matching, backend/type failures crash. |
| H. Model/business separation | PASS | Tested deterministic routing and no model-accessible payment tool. Unverified model facts and unconstrained narrative remain weaknesses. |
| I. Injection awareness | PARTIAL | Prompt labels, regex checks, deterministic block and restricted tool surface exist; fact poisoning and narrative injection remain possible. |
| J. Human-approvable resolution | PARTIAL | Live packet has facts/rationale/draft; wrong recommendations, missing checks and brief fallback limit reliability. |

**Reliability findings**

| Failure mode | Current handling and verification |
|---|---|
| Malformed JSON | Partial. Tested fence/trailing-comma recovery and garbage rejection. Individual-field salvage parsed malformed `1.2e4` as `1.2`. Repair failure can continue via regex. |
| Markdown fences | Tool-argument fenced JSON parsed in test. Fenced prose without a tool call is rejected and triggers repair/fallback. |
| Missing required fields | Missing keys flagged, but coercion may fill them. Simulated API responses with null currency or invoice number passed validation and reached `approve_match`. |
| Wrong PO extracted | Unknown IDs route to information request. A simulated wrong existing PO with mutually consistent wrong vendor/amount reached matched; no source-to-extraction verification exists. |
| PO not found | Live unknown-PO fixture correctly requested information with approval required. |
| Vendor mismatch | Live obvious mismatch escalated. Probe `Logistics` falsely matched `ABC Logistics`. |
| Currency mismatch | Explicit EUR/USD mismatch escalated in probe. Missing currency was treated as matching. |
| Line items differ from total | No schema/check. An inconsistent source with 11000 + 450 and total 12000 reached matched under controlled extraction. |
| Missing/invalid amount | Missing amount escalated in probe. Ordinary invalid strings flagged by validator; null allowed. Negative, boolean and NaN amounts accepted; simulated API negative/NaN values generated nonsensical short-pay recommendations. |
| Backend returns None | PO and vendor None each produced TypeError in resolve_invoice. Paid-invoice None is expected and handled. |
| Missing vendor/policy | Error/missing tolerance defaulted to $1; a matching invoice still reached approve_match. vendor_found is not a routing prerequisite. |
| Contradictory generated brief | Mocked `Payment approved. Send $99,999 immediately.` was returned verbatim despite a held disposition. Structured disposition remained unchanged. |
| Hallucinated facts | No evidence validation. Wrong existing facts accepted in controlled extraction; free-form brief unchecked. |
| Runtime failures | Extraction exceptions partly handled, brief exceptions hidden, backend/type/audit/file-read exceptions lack an overall safe-review path. None/type crashes reproduced; disk/read faults identified statically. |
| Previously paid PO | Live exact paid invoice escalated. Changing invoice number on paid PO produced matched in probe; po_status is recorded but unused. |
| Evaluation with model unavailable | All six existing fixture checks still passed with extraction forced to fail. Fallback is not a failure criterion. |

**Prioritized issues and minimal fixes**

No CRITICAL issue was established: this implementation has no payment execution or autonomous approval action. HIGH findings concern incorrect recommendations and failed safeguards for the human approver.

1. **HIGH — Incorrect financial routing** (`agent.py:299`, `backends.py:160`). $11,000 against $12,000 recommends paying $12,000 and says the invoice exceeds PO by -1000. Add distinct underbilling/overbilling branches; do not recommend paying above the invoice. Reject nonfinite, boolean and unsupported negative amounts. Use Decimal or integer cents. Configure the requested $100 tolerance explicitly and test boundary values.
2. **HIGH — Incomplete business prerequisites** (`agent.py:185`, `backends.py:168`). Require valid PO, payee, invoice ID, currency, finite amount and known vendor policy before match recommendations. Null business fields must mean review, not a match. Make notes optional. Do not guess a policy when lookup fails.
3. **HIGH — Vendor identity and paid-state bypass** (`backends.py:92`, `agent.py:628`). Replace substring/token matching with normalized exact names and explicit aliases tied to vendor IDs. Check paid/closed PO status. Scope paid invoice identifiers to vendor identity to avoid unrelated vendors' invoice-number collisions; current collision concern is static.
4. **HIGH — Extraction recovery hides failure / facts ungrounded** (`agent.py:337`, `agent.py:571`). Do not salvage monetary fragments into actionable facts. Permit strict JSON plus a simple fence strip and one repair; otherwise emit HUMAN_REVIEW_REQUIRED with a reason. Regex can supply clearly marked candidate fields for a clerk, but must not restore normal approval routing. Validate copied evidence for critical facts and flag ambiguous/conflicting references.
5. **HIGH — Missing line-item reconciliation** (`agent.py:44`, `backends.py:160`). Add minimal line-item amounts to extraction and check sum versus invoice total in deterministic code; include defined taxes/fees if supported. Fail to review when reconciliation is incomplete or inconsistent.
6. **HIGH — Workflow can crash** (`agent.py:628`). Normalize/validate lookup results, catch backend failures at the orchestration boundary, and return a review packet. Validate all field types before normalization/lookups. Handle file/audit errors explicitly without implying a successful completed workflow.
7. **MEDIUM — Generated resolution not trustworthy** (`agent.py:467`). Send only allowlisted validated facts and deterministic status to the writer; omit raw notes. Keep authoritative status/amounts in a deterministic visible section. Require a constrained summary and validate it or use a deterministic fallback; log empty/error/truncated generation. The live trace exhausted the 220-token brief limit with empty final content; adjust the local generation budget or server reasoning settings and re-test before claiming this path works. Remove unsupported 5-business-day policy and make email wording contingent on human approval (`backends.py:223`).
8. **MEDIUM — Demo evaluation overclaims success** (`run_mvp.py:131`). Distinguish model-extraction success, fallback/review correctness and routing correctness. Assert exact delta, tolerance, required status, human gate and required field validity. Include failure probes as regression cases with desired assertions. Report model/brief trace and failure reason clearly.
9. **MEDIUM — Missing email and explicit statuses** (`run_mvp.py:163`). Add optional `--email` input, mark both documents untrusted, extract evidence and surface conflicts. Introduce explicit HUMAN_APPROVAL_REQUIRED for validated proposals and HUMAN_REVIEW_REQUIRED for uncertain/invalid cases without adding a framework or a UI.
10. **MEDIUM — Live-demo predictability** (`agent.py:332`, `agent.py:414`, `requirements.txt:1`). Actual client defaults are a 600-second read timeout and two retries. Set bounded timeouts/retries; handle output truncation; pin the tested dependency version; document llama-server startup/model path and healthy-endpoint check. These prevent hangs and make setup explainable. No timing SLA was tested.
11. **LOW — Clarity and redundant paths.** `decide_disposition` receives unused extraction-context arguments po/vendor; JSON salvage, regex fill and broker correction overlap and obscure provenance. Simplify recovery after strict validation is in place. Preserve the separate Part 1 experiment. Add audit timestamp/source references rather than a database. This remains a small Python project with appropriate dependencies; no LangChain, Docker, classes or redesign is needed.

**Prompt-injection assessment**

Prompt-level protection exists, but delimiters and regex are not security boundaries. The user's exact example was blocked in a controlled probe; the live bundled injection fixture was also escalated, using regex fallback. Another instruction to replace extracted amount/currency produced no regex hits. That demonstrates detector incompleteness, not that this wording successfully attacks LFM.

Architecture-level protection is stronger: Python always performs lookups and decides routing; the extraction tool cannot send payment or approve anything. A malicious tool name is rejected rather than dispatched. However, an attacker need only influence PO/vendor/amount to affect the deterministic recommendation. Source facts are not verified, and recovered regex facts also come from the attacker-controlled document. Optional brief generation receives raw extracted notes without an explicit untrusted-data boundary and accepts contradictory text. The mock contradictory-brief test confirms the unchecked output path, not an observed live exploit. Preserve the restricted tool surface and human gate while validating facts; do not claim the system prompt prevents injection.

The security skill's available references cover Python web frameworks, not this plain Python CLI; these security conclusions are repository inspection and test findings, not framework-specific certification.

Implement items 1–4 and 6 first: correct financial recommendations, strict prerequisites, exact vendor/paid-state checks, safe extraction failure, and backend guards. Then add line items, email ingestion, explicit statuses, and honest evaluation/brief traces. No fixes were applied because the user requested review and recommendations first.

## Fix verification: after the original review

Implementation follows the original review while retaining the existing CLI, mock backends, extraction tool, policy function and packet format. The files present at the start of implementation differed from the reviewed snapshot; current CLI status/email changes and the dependency pin were retained and completed.

The highest-risk fixes are exact monetary calculations, required source-backed facts, explicit USD policy, exact vendor identity, paid-state checks, and a review-required result for extraction/backend/audit failures. Extraction keeps commercial fields and line items small; Python independently locates supporting original source lines without filling missing model facts. Optional LFM prose is constrained to approved sentences because a second free-form model judgement would not reliably validate its factual claims.

The [repository README](../README.md) documents current setup, commands, statuses and supported limits. The original review above and its probe results are historical evidence; `probe_failures.py` targeted the pre-fix API and is superseded for regression testing by the current tests in `part2/`.

Validation completed on the revised implementation:

- 44 offline unittest methods passed (including parameterized failure cases); see `fixed-regression-tests.log`.
- The real invoice_001 plus vendor_email_001 run completed locally: extraction 15.88 seconds (one attempt), generated brief 15.85 seconds. Exact delta `450.00`, tolerance `100.00`, status `HUMAN_APPROVAL_REQUIRED`, auto-post false, audit written. See `fixed-invoice-email.log`.
- Unreadable custom input produced a visible `HUMAN_REVIEW_REQUIRED` / `input_failure` packet without a traceback; see `fixed-input-error.log`.
- Earlier nested-evidence extraction experiments failed or timed out and were removed. The final schema asks for commercial facts and line amounts; source validation remains deterministic and cannot supply missing extracted facts.
- Final real-server fixture evaluation: **5/5 passed** using `--case all --no-brief`. All four ordinary invoices extracted successfully on their first attempt; the injection fixture correctly skipped inference. Live extraction latencies were 19.98, 104.38, 59.59 and 43.10 seconds. The optional LFM brief was tested separately on the invoice/email example above. See `fixed-live-fixtures.log`.

All requested implementation work and checks are complete. Local generation latency remains variable; the explicit timeout and review-required failure path are intentional. These successful runs demonstrate the tested fixtures, not universal extraction accuracy.
