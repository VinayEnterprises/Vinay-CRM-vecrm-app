# VECRM-L29 — Halt cadence is structural

**Status:** Active
**Earned in:** S33 (6 documented incidents)
**Date:** 2026-05-27 (S33 close)

---

## Statement

When a dispatch includes a halt instruction with a specific paste-back request, the operator MUST execute the named step, paste the requested output, and wait for dispatcher confirmation before executing any subsequent step. Halts MUST NOT be chained — running multiple halt-gated steps and pasting their combined outputs at once forfeits the dispatcher's ability to catch drift mid-sequence and constitutes a documented failure of the cadence.

This rule applies symmetrically to deploy chains, smoke matrices, regression sweeps, recon sequences, and any other multi-step procedure where the dispatcher has written "Halt" between steps.

## Why it exists

S33 produced 6 documented halt-chain-skip incidents (OBS-S33-E, H, L, plus three additional during disk-pressure tranche execution, smoke matrix run, and SAM-33-3 portal verification). The pattern repeats across operational categories — housekeeping, deploy, smoke — meaning it is not a category-specific lapse but a structural cadence failure.

The cost of chaining halts shows up in three specific failure modes that occurred in S33:

- **OBS-S33-T (false alarm on Contact Date deletion).** The dispatcher misread a `git diff` hunk as a regression because the surrounding file context wasn't visible. If the next step had chained without halt, the dispatcher would have authored a "Fix D restoration" edit that would have *introduced* a duplicate Field row. The halt caught the misdiagnosis before the operator made a damaging edit.
- **OBS-S33-R (reachability-test design defect).** A regression test was authored with insufficient positional arguments to the `convert_lead_to_inquiry` whitelisted method, producing a 500 TypeError that the dispatcher initially interpreted as a deploy regression. The halt allowed re-running R3 with a complete argument set, revealing the test was wrong, not the deploy.
- **OBS-S33-U (Frappe NULL semantics).** SAM-33-3-g looked clean to the operator at the moment (Overdue chip filtered to 11 leads). Only because subsequent halt-gated DB verification was requested did the discrepancy surface (DB ground truth: 0 overdue rows). Chained verification would have shipped the Phase 1 portal with the bug latent in production.

In each case, the halt was the load-bearing artifact. The dispatcher's "looks right" judgment alone, without verification cadence, would have shipped or worsened bugs.

The structural argument: halt cadence is the mechanism by which two-party (operator + dispatcher) execution catches errors that either party alone would miss. Eliminating it collapses the system to a single point of verification, defeating the design.

## How to enforce

The dispatcher's responsibility:

1. Every dispatched procedure with more than one step MUST include explicit "Halt" markers between independent steps.
2. Each halt MUST include a specific paste-back request (e.g. "paste `git log --oneline -3`", "paste the curl output including HTTP_STATUS line").
3. The dispatcher MUST acknowledge the paste-back and confirm the step is clean before issuing the next dispatch.
4. If the dispatcher dispatches a multi-step sequence with halts and the operator returns combined output for multiple steps, the dispatcher MUST treat this as a documented incident and surface it explicitly in the next response.

The operator's responsibility:

1. Read the dispatch end-to-end before executing.
2. Identify halt markers explicitly. Execute only up to the first halt.
3. Paste the requested output.
4. Wait for confirmation. Do not infer "I know what comes next" and proceed.
5. If a halt's paste-back request feels redundant or excessive in the moment, the operator may push back in chat — but MUST NOT silently bypass it.

Operator and dispatcher are equally accountable for the cadence. Chained output is not "operator error" alone; it is also a sign the dispatcher's halt markers were unclear or the sequence was too long for the moment.

## Acceptable exceptions

There are two narrow exceptions to chaining prohibition:

1. **Strictly read-only, idempotent recon commands** that the dispatcher has explicitly grouped as "run together, paste together" with a single halt at the end. Example: `git status` + `git log --oneline -3` + `git diff --stat`. The dispatcher must mark these explicitly as a batch; absent that marking, the default is one-step-per-halt.

2. **Operator-declared override in chat.** If the operator says explicitly "I'm going to chain the next N steps because [reason]", that constitutes a documented choice. The dispatcher should acknowledge and adapt, but the chained-skip cost (loss of mid-sequence drift detection) belongs to the operator for that batch.

Both exceptions require explicit declaration. Silent chaining is the failure mode this lock exists to prevent.

## Bypass conditions

None. There is no production emergency that justifies bypassing halt cadence — emergencies are exactly when verification matters most. A bug found mid-deploy because cadence was honored is cheaper than a bug found post-deploy because cadence was skipped.

## Reconciliation when violated

When a halt-chain-skip is detected (either party):

1. Surface it immediately in chat. Name the incident. Do not let it pass silently.
2. Bank as an OBS-Sxx-N observation in the close handover.
3. After 5 documented incidents within a single session, the operator and dispatcher MUST pause and review whether the cadence has decayed structurally (fatigue, dispatch length, complexity) and adjust the working session accordingly — break, shorter dispatches, change of pace.

## History

| Session | Incidents | Notes |
|---|---|---|
| S32 | (not tracked as halt-skip category) | Heredoc-discipline lock candidate dominated the discipline category that session |
| S33 | 6 | Hard promotion incident threshold reached. Lock formalized. |

This lock supersedes the informal "halt cadence" guidance referenced in prior session closes. The L29 designation establishes it as an architectural invariant on par with VECRM-L8 (dual-surface verification) and VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE.

---

## Companion observation

OBS-S33-D notes that zsh multi-line `git commit -m` folds newlines into spaces, requiring `-F -` heredoc or repeated `-m`. This is operationally adjacent to L29 — both are "discipline at the moment of execution" patterns. Operators may find it useful to think of L29 (halt cadence) and the heredoc pattern as the same mental category: *do not collapse multi-step work into a single submission*.
