# VECRM-S20-B — Carry-forward content audit gate: "prove this is real" before further preservation

**Status:** Active
**Earned in:** S20 Phase 3 (Item 6 closure under Definition 2)
**Date:** 2026-05-20

---

## Context

Item (6) — voucher_counter.py docstring micro-correction — had been carried as pendency since S15-Gate-5 across five sessions. At S20, when scoped for closure, recon revealed no concrete content actually existed to fix. The carry-forward was a memory of "something needed fixing" without specifying what or where. Closed under Definition 2 (retired after audit, no edit needed).

The pattern this surfaces: carry-forward items can persist across sessions on the strength of memory alone, accumulating apparent legitimacy without ever being audited for whether the underlying content is real and recoverable. By session 5+ of carry, no participant remembers the original specifics; the item exists because it exists.

## Decision

Carry-forward items without concrete, recoverable content are subject to a "prove this is real" audit gate before further preservation. Concretely: any pendency carried across two or more sessions without explicit file/line/symbol references must, on next adjudication, either:

(a) Have its concrete content re-derived from source (filesystem, git log, code) and pinned in the pendency register with file + line references, OR
(b) Be closed under Definition 2 — retired after audit — and removed from the active queue.

Items that fail audit (no recoverable concrete content found) close under Definition 2 immediately, regardless of how many sessions they have been carried.

## Operational implications

- Pendency register entries that are carried for two or more sessions should include file paths, line numbers, or symbol names — not just narrative descriptions.
- At session open, the recon phase explicitly audits any pendency carried 2+ sessions. If concrete content cannot be located in current source, the item is Definition-2-closed at Gate 1, not deferred forward.
- Narrative-only carry-forwards ("X needs review", "Y should be cleaned up") that have lost their concrete specifics are treated as auditable claims, not as inherited obligations.
- The closing audit's negative finding ("no content found") is itself sufficient documentation for closure. No code change is required to close an item under Definition 2.

## Reversal conditions

This lock is reversible if it produces a false-positive closure — i.e., a real concrete issue gets Definition-2-closed because its specifics were lost across sessions and re-derivation failed. If that occurs, the operating model should incorporate stricter carry-forward serialization (concrete content captured at first carry, mandatory for forward preservation) rather than weakening the audit gate itself.

No such false positive has been observed through S20.

## Relationships

- **VECRM-S19-F** (cross-session prose-vs-source discipline) — VECRM-S20-B is the carry-forward-specific application of S19-F. S19-F says "verify against source not against handover prose"; S20-B says "if you can't find the source content, close the item, don't carry the prose forward."
- **VECRM-S19-A** (fetch + verify before assuming Mac state) — sibling discipline; both are anti-trust-of-memory principles applied at different scopes (session-state vs. pendency-state).

## Verification

S20 Item (6) closure under Definition 2 is the founding case. Closing artifact: S20-close-handover §1 Phase 3 record; no PR required since no code change occurred. Pendency register entry retired at S20 close.
