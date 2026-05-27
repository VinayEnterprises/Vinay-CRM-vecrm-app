# Session 32 — Close Handover

**Date:** 2026-05-26 (single-day session, ~17h)
**Operator:** Ajay Salvi
**Dispatcher:** Claude
**Outcome:** ✅ Clean close. 0 active blockers. Both TV and EV self-service flows live in production.

---

## Headline

S32 entered with a P0 blocker (PD-S32-TV-SUBMIT-417) that broke Travel Voucher
submission for all non-Admin roles, and a P1 commitment (PD-S25-PORTAL-SUB-B-
EXPENSE-VOUCHER) for the Expense Voucher portal half. Both shipped clean.

Net deliverables:
- TV self-service unblocked for Sales Head, Head of Engineers, Admin self-submit,
  and Admin on-behalf (PR vecrm #44).
- EV backend endpoints live (PR vecrm #45).
- EV portal complete: list, detail, new form, multi-line compose, eager receipt
  upload, role-scoped list filtering, admin on-behalf dropdown, nav (TopBar +
  MobileNav). PR vecrm-portal #30.

11 PRs merged across this session (8 prior + #44 + #45 + portal #30).

---

## Repo state at close

| Repo | Branch | HEAD | PR |
|---|---|---|---|
| vecrm | main | `2cf1988` | #45 |
| vecrm-portal | main | `5d9ac18` | #30 |

Production:
- Backend image rebuilt + recreated 2026-05-26T16:41 UTC via canonical 8-step.
- Portal Vercel deploy live by 17:18 UTC.
- Rollback tags on VPS: `s32-pre-pr44-rollback`, `s32-pre-pr45-rollback`.

---

## P0 root cause (banked for institutional memory)

**PD-S32-TV-SUBMIT-417** — The TV controller's `before_insert` hook in
`vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py` line 76 throws
HTTP 417 when `emp.role not in APPROVER_SETS`. `APPROVER_SETS` (line 27) had
only 2 keys (`Sales Rep`, `Field Engineer`), a holdover from S22 when Admin
was the sole submitter. When S32 self-service shipped (PRs #43 + portal #29),
Sales Head / Head of Engineers / Admin became valid submitters but this
eligibility gate was never updated.

The error was invisible because:
1. `frappe.throw` for ValidationError doesn't always populate `_server_messages`,
   so the portal BFF's `humanizeError(417, ...)` fell through to its generic
   fallback "Your input was rejected. Please check the form."
2. Frappe doesn't log thrown ValidationError to `tabError Log`.
3. The image was using gunicorn with access logging disabled, so backend
   container logs had no POST trace.

Fix: PR vecrm #44 expanded `APPROVER_SETS` to all 5 submitter roles
(Sales Rep / Field Engineer / Sales Head / Head of Engineers / Admin), each
mapped to their approver set per the operator-locked role matrix.

**Lessons:** When extending self-service to new roles, audit ALL controller
hooks (`before_insert`, `validate`, `before_submit`, `on_submit`) for hardcoded
role gates, not just the auth path.

---

## EV Phase 2 — locked decisions (architectural record)

The full set of Q-EV-* operator locks now ratified in code:

| Lock | Value |
|---|---|
| Q-EV-CONFIRM-1 categories | Hotel / Food / Supplies / Communication / Misc (no schema change) |
| Q-EV-2 receipt required | Per line, endpoint-enforced |
| Q-EV-3 file constraints | jpg/png/pdf, 5MB cap, triple-enforced (component + BFF + Frappe) |
| Q-EV-4 currency | INR only, ₹ symbol |
| Q-EV-5 draft persistence | Server-side after Review (mirror TV) |
| Q-EV-6 submitters | Sales Rep, Field Engineer, Sales Head, Head of Engineers (self) + Admin (on-behalf). HR NOT a submitter. |
| Q-EV-7 approval UI | Out of scope this session — Desk for now (Phase 3 = PD-S29-VOUCHER-APPROVER-PORTAL-B2) |
| Q-EV-CONFIRM-ATTACH | (b) endpoint-level enforcement (doctype reqd=0 preserved for Desk corrective) |
| Q-EV-RECEIPT-VERIFY | ON — backend checks `frappe.db.exists("File", {"file_url": attachment})` |
| Q-EV-RECEIPT-FLOW | 2-step (upload returns URL → URL in voucher payload) |
| Q-EV-UPLOAD-PATH | (a) Frappe `/api/method/upload_file` directly |
| Q-EV-LINE-UPLOAD-TIMING | (a) eager on file pick (matches PD-S30 leads pattern) |
| Q-EV-LIST-FILTER | BFF role scoping (admin all, non-admin own) |
| Q-APPROVER-SETS-1..4 | Per PR #44 dict |

---

## Smoke matrix outcomes

### SAM-44 (TV after PR #44 fix)
- SAM-44-1 Mohit self-submit → VE/TV/00095/26-27 ✅
- SAM-44-2 Ajay self-submit → VE/TV/00096/26-27 ✅
- SAM-44-3 Ajay on-behalf for Mohit → VE/TV/00097/26-27 with snapshot
  `submitter_role=Sales Head` (correct) ✅
- SAM-44-4 cross-submit rejection → 403 (correct) but UX copy reads
  "session expired" — banked as **PD-S32-NEXT-VOUCHER-PERMISSION-ERROR-UX**
- SAM-44-5 list intact, 71+ vouchers visible ✅

### SAM-45 (EV)
- SAM-45-1 + SAM-45-2 Mohit multi-line EV → VE/EV/00014/26-27, 3 lines,
  ₹1950, Submitted ✅
- SAM-45-3 file validation (size + type) ✅ (operator confirmed without screenshot)
- SAM-45-4 Admin on-behalf (Ajay → Anil) → VE/EV/00015/26-27, submitter is
  Anil's phone, role snapshot=HR (Anil is HR) ✅
- SAM-45-5 cross-submit bypass attempt → STATUS 403 ✅ (same UX-copy bug
  as SAM-44-4, already banked)
- SAM-45-6 list role scoping → Mohit sees own 2, Ajay sees Anil's via
  admin-all path ✅

VE/EV/00013/26-27 is a Mohit draft (he closed before submitting). Harmless.

---

## OBS bankings new in S32

| Code | Lesson |
|---|---|
| OBS-S32-T | macOS BSD `cat -A` doesn't exist; use `cat -et` or `xxd` for whitespace inspection |
| OBS-S32-U | For Python-generated source files, use `ast.parse` pre-flight check before writing |
| OBS-S32-V | Multi-line JSX attribute lists with closing `>` on own line trigger SWC parse errors; prefer single-line attributes for simple-child elements |
| OBS-S32-W | Parent-narrow + child-loose React component type pairs: type child prop as plain `string`, parent casts via `as Partial<ParentType>` |
| OBS-S32-X | Python heredoc `\\n` becomes literal text `\n` in file (not newline). Use `chr(10)`, or **prefer `sed -i ''` for single-line surgical inserts on macOS**. This rule had 4 violations in S32 — promotion candidate for S33. |

---

## Lock promotion candidates for S33

1. **Heredoc-discipline lock** — 4 violations this session (all OBS-S32-X
   instances). Rule: single-line file inserts → sed; >50 line file creation →
   Python heredoc with `chr(10)` newlines. If one more violation in S33,
   formalize as architectural lock.

2. **Dispatcher-spec-calibration meta-lock** — banked since S30, still
   candidate. Pattern: dispatcher reads from prior session memory rather
   than verifying actual file state, causing spec drift. Mitigated this
   session by aggressive use of `view` + `grep` recon before authoring.

---

## Session metrics

- Total session duration: ~17h (06:30 IST start → 23:35 IST close)
- Hard stop budget: 03:30 IST (next morning) — used 50% of buffer
- PRs merged: 11
- P0 blockers active at close: **0**
- P1/P0 pendencies closed: 7 (see pendency doc for full list)
- Lines of code shipped: ~2,000 production code + ~1,200 tests/probes
- Heredoc retries: 4 (all on the same `\n` pattern — see OBS-S32-X)
- Critical recon pivots: 2 (single-file-vs-split detail page per OBS-S22-B;
  HR-vs-Sales-Rep on Anil role snapshot)

---

## Final acknowledgments

S32 was the longest single-day session in VECRM history but landed clean.
Three factors made the close possible:

1. **Halt-on-drift discipline** — operator consistently halted after each
   verify step, paste output, get next dispatch. Zero pushed-through-anyway
   failures.

2. **Recon-before-write** — every new file or patch preceded by `view` or
   `grep` to confirm actual current state, not assumed state.

3. **Rollback tags on VPS before each deploy** — both `s32-pre-pr44-rollback`
   and `s32-pre-pr45-rollback` exist on the VPS image registry. Either deploy
   can be reverted in <60s if a regression surfaces in production use over
   the next 24h.
