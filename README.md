# Invoice exception handling for a freight broker

A mid-market freight broker’s accounts-payable team spends most of its exception time reconstructing context, not making the payment decision. The business goal is to prepare a checked, explainable packet for each exception so a person can approve, edit, or escalate—without giving software authority to pay.

Northline Freight Brokerage is a fictional customer. The volumes, labor rates, and savings figures below are planning assumptions for discovery, not measured results.

---

## The operating problem

Carriers bill for completed loads. The transportation management system already holds the agreed purchase order. Invoices still arrive as PDFs, scans, photos, and emails, with inconsistent headings, payee labels, and charge descriptions.

Straightforward invoices can follow existing matching rules. Exceptions still require a clerk to:

- Find the invoice and the matching purchase order
- Distinguish the carrier (payee) from the broker named on the letterhead
- Check whether printed charges add up to the invoice total
- Compare that total with the purchase order and the allowed variance
- Draft the next action: pay as billed, short-pay, request backup, or escalate

That reconstruction is repetitive. It is also where delays and mistakes accumulate: the wrong payee, a duplicate payment, or a surcharge paid without evidence.

**Resolution, for this process, means a documented proposal or a specific information request.** It does not mean executing payment or settling whether a disputed charge is contractually owed.

---

## Why the work is expensive

| Assumption | Value |
|---|---:|
| Carrier invoices per month | 15,000 |
| Share that need exception review | 20% |
| Exceptions per month | 3,000 |
| Active handling time today | 8 minutes each |
| Loaded AP labor cost | $45 per hour |
| Monthly exception effort | 400 hours |
| Monthly labor capacity represented | $18,000 |
| Annual labor capacity represented | $216,000 |

`15,000 × 20% × 8 ÷ 60 = 400 hours/month`. `400 × $45 = $18,000/month`.

A reasonable service target is an **initial disposition within one business day**, with an earlier cutoff for exceptions that affect the next payment run. Vendor reply time and final approval remain separate from preparation time.

---

## What success looks like

Each exception produces a packet a reviewer can inspect:

- Carrier, invoice, purchase order, currency, amount, and line items, with the source lines they came from
- A comparison against the purchase order and vendor policy (for example, invoice **$12,450**, PO **$12,000**, difference **$450**, above a **$100** tolerance)
- A proposed next action, such as paying the PO amount and asking the vendor for backup on the variance
- A draft vendor email
- An audit record of the recommendation

**The human retains payment authority.** No payment is posted and no email is sent until a person decides.

The example case is typical of the queue: the invoice names the broker prominently, remits to a different carrier, and adds a fuel surcharge to the agreed freight. The layout is an extraction problem; the extra charge is a policy and evidence problem.

---

## Who this is for

| Stakeholder | What they care about |
|---|---|
| Controller / finance | Cost of exceptions, payment controls, auditability |
| AP manager and clerks | Backlog, repeated lookups, a handoff they can trust |
| Carrier operations | Faster, clearer responses on billing disputes |
| IT / security / TMS owner | Where documents are processed, who can access them, how records are retained |

---

## The value hypothesis

If useful packets cover **60%** of the queue and cut active handling on those cases from eight minutes to three, the operation releases about **150 hours per month** (`3,000 × 60% × 5 ÷ 60`). The remaining 40% keep the full eight-minute effort.

| Share of the queue with a useful packet | Capacity released / month | Gross monthly capacity value |
|---|---:|---:|
| 30% | 75 hours | $3,375 |
| 60% | 150 hours | $6,750 |
| 80% | 200 hours | $9,000 |

This is **released capacity**, not a promised headcount reduction. It is also before infrastructure, integration, support, and residual review cost. The practical benefit may be absorbing more volume, reducing overtime, or answering carriers sooner. Those outcomes have to be measured.

At an illustrative $1,000 monthly operating cost and $10,000 setup cost, the 60% scenario implies about **$59,000** of first-year net capacity value. Capacity value becomes cash only if the organization can avoid spend or redeploy the time.

---

## What would invalidate the case

- Exception volume is too low, or clerks already finish each case quickly
- Too many arrivals are photos, degraded scans, or layouts the process cannot read
- Reviewers still redo every lookup and calculation, so the packet does not save time
- Proposal errors (wrong vendor, wrong amount) are higher than finance will accept

The next step is a shadow pilot on permissioned historical exceptions: freeze the quality bar first, compare assisted handling with the current process, and proceed only if coverage and saved effort justify the full operating cost.
