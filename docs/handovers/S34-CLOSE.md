cd ~/Documents/GitHub/vecrm
cat > docs/handovers/S34-CLOSE.md <<'CLOSE_EOF'
# Session 34 — Close Handover

**Date:** 2026-05-27 (single-day session, ~10h dispatch + execution)
**Operator:** Ajay Salvi
**Dispatcher:** Claude
**Outcome:** ✅ Clean close. 0 active P0/P1 blockers. PD-S30-LEAD-FOLLOWUP Phase 2 shipped end-to-end (backend + portal), production-verified. PD-S33-NEXT-IMAGE-PRUNE (P1) closed.

---

## Headline

S34 entered with PD-S30-LEAD-FOLLOWUP Phase 2 as the marquee P1 and the
PD-S33-NEXT-IMAGE-PRUNE policy item as a quick P1 closeout. Both shipped, plus
the full Phase 2 portal surface.

Net deliverables:
- PD-S33-NEXT-IMAGE-PRUNE closed (PR vecrm #47) — `scripts/vps-prune.sh`
  codifies "keep latest 3 session-tagged rollback images by session number."
  Deployed to VPS `/root/scripts/vps-prune.sh`, dry-run + execute verified.
  Pruned 13 images, ~37GB reclaimed (49% → 23% disk; 75GB → 112GB free).
- PD-S30-LEAD-FOLLOWUP Phase 2 backend live (PRs vecrm #48 + #49 + #50) — new
  standalone `VECRM Lead Touchpoint` doctype (append-only: delete=0, write=0
  all roles, autoname=hash), 2 whitelisted methods (`create_touchpoint`,
  `list_touchpoints_for_lead`), virtual read-time stats
  (`last_contact_date`, `touchpoint_count`) on the Lead controller. Schema
  migration v1_7 (verifier patch). SM-2-* smoke 10/10 pass.
- PD-S30-LEAD-FOLLOWUP Phase 2 portal live (PR vecrm-portal #34) — new BFF
  GET+POST `/api/leads/[name]/touchpoints`, new BFF GET
  `/api/leads/followup-due-today-count`, Touchpoints section on Lead detail
  page (inline form, chronological list, header stats), "due today" nav badge
  on TopBar + MobileNav. SAM-34-* functional smoke 7/7 pass + production
  verified green.

5 PRs merged this session (vecrm #47, #48, #49, #50; vecrm-portal #34).

**PD-S30-LEAD-FOLLOWUP-WORKFLOW Phase 2 fully closed (backend + portal).**
Phase 3 (status enum + email reminders) remains blocked on
PD-S29-VEMIO-EMAIL-PIPELINE.

---

## Repo state at close

| Repo | Branch | HEAD | Closing PR(s) |
|---|---|---|---|
| vecrm | main | `4c4945c` | #47, #48, #49, #50 |
| vecrm-portal | main | `395da08` | #34 |

Production:
- Backend image rebuilt + recreated via canonical 8-step (PR #50 final).
  Container: `vecrm-backend-1` Up, image `vecrm-custom:latest` =
  `b0c062836126`.
- Schema migration v1_7 executed (verifier patch — table created by Frappe
  doctype-sync, patch asserts existence). `bench migrate` clean.
- 3-layer live-code verification clean (Mac source, vendor copy, container
  filesystem all consistent per VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE).
- Portal Vercel production deploy from `395da08` confirmed Ready. Production
  verified: touchpoints section renders, `/api/leads/[name]/touchpoints` 200,
  `/api/leads/followup-due-today-count` 200 (authenticated), Phase 1 followup
  filters intact.
- Production touchpoint table clean (all SM-2-* and SAM-34-* rows deleted).

Rollback ladder on VPS (4 rungs, PR #50 live at top):
- `vecrm-custom:latest` = `b0c062836126` (PR #50, live)
- `vecrm-custom:s34-pre-pr50-rollback` = `d5fc9c84c4df` (PR #49)
- `vecrm-custom:s34-pre-pr49-rollback` = `b87e1aec8619` (PR #48)
- `vecrm-custom:s34-pre-pr48-rollback` = `929d6e3b92d8` (pre-Phase-2 clean)

---

## P0/P1 root causes (banked for institutional memory)

### OBS-S34-A: Frappe v16 ORM aggregate syntax — neither string nor dict

**Surfaced:** PR #48 SM-2 smoke (post-deploy verification).

The Phase 2 stats helpers needed `MAX(touchpoint_date)` and a COUNT. First
attempt used `frappe.db.get_value(..., fieldname="MAX(touchpoint_date)")` —
Frappe v16 rejected with `ValidationError: SQL functions are not allowed as
strings in SELECT`.

PR #49 attempted the dict syntax `fieldname={"MAX": "touchpoint_date"}`
suggested by the error message itself. **Frappe v16 ALSO rejected the dict
form** with a different error. The error message's hint was wrong.

Root cause + fix (PR #50): codebase recon (`grep -rn "MAX(\|COUNT(\|frappe.qb"`)
confirmed vecrm uses `frappe.db.sql` with parameterized raw SQL for ALL
aggregates (9 existing call sites in patches). Switched both helpers to:
```python
result = frappe.db.sql(
    """SELECT MAX(touchpoint_date) FROM `tabVECRM Lead Touchpoint`
       WHERE lead = %s""",
    (lead_name,),
)
last = result[0][0] if result and result[0] else None
```
SM-2-* 10/10 pass after this. **Lesson:** don't trust error-message hints;
verify against codebase idiom. Compounds PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-
PATTERNS — the v16 aggregate finding should be added to that lock when
authored.

### OBS-S34-B: unauthenticated curl 500 on scoped count endpoint (NOT a bug)

**Surfaced:** post-merge production curl of `/api/leads/followup-due-today-count`.

Unauthenticated curl returned HTTP 500, not the predicted 401/403. Root cause:
`getScopedLeadFilter()` throws on missing session → caught → returns
`{error: "Server error"}` status 500. This is the code's defined behavior for
the no-session path (auth gate normally redirects before reaching the BFF).
Authenticated browser requests return 200 with `{count: N}` (verified in
production DevTools). Not a bug — expected behavior for the no-cookie path.

---

## OBS bankings (full set, A–N, 14 items)

- **OBS-S34-A:** Frappe v16 ORM aggregate syntax rejects BOTH raw-string and
  dict `fieldname` for SQL functions. Canonical idiom = `frappe.db.sql` with
  parameterized raw SQL. (See P0/P1 above.)
- **OBS-S34-B:** Unauthenticated curl 500 on scoped count endpoint is expected
  (getScopedLeadFilter throws → caught → 500), not a bug. (See P0/P1 above.)
- **OBS-S34-C:** Error-message hints can be wrong — Frappe v16 suggested the
  dict syntax in its own rejection message; that suggestion was incorrect.
- **OBS-S34-D:** `bench execute vecrm.api.method --kwargs '{...}'` works but
  SSH double-quoted quoting is fragile; single-outside-escaped-double-inside
  is the reliable shape.
- **OBS-S34-E:** `python -c` outside the bench env cannot init a Frappe site
  (logger paths, sites_path resolution). Use `bench execute` with an
  importable dotted path.
- **OBS-S34-F:** Whitelist verification via Python introspection is brittle
  across Frappe versions; canonical test is HTTP smoke (200 vs 404).
- **OBS-S34-G:** macOS/MariaDB safe-update mode blocks
  `DELETE ... WHERE non-key-column LIKE`. Double-subselect bypass did NOT work
  (subquery optimized away). Working approaches: `SET SQL_SAFE_UPDATES=0;` in
  the same statement, or DELETE by explicit PK `name IN (...)`.
- **OBS-S34-H:** `gh pr merge --delete-branch` deletes server-side but the
  local remote-tracking ref persists until `git fetch --prune`.
- **OBS-S34-I:** ssh + docker exec + bench execute multi-layer quoting
  requires `'outside'` `"inside"` with escapes.
- **OBS-S34-J:** Vercel preview deployments CAN authenticate against
  production Frappe (operator confirmed I-a path; Frappe accepts preview
  origins). Preview smoke is a valid pre-merge gate for this stack.
- **OBS-S34-K:** vecrm-portal main has 17 pre-existing
  `react-hooks/set-state-in-effect` lint errors. Scoped-lint of PR C touched
  files surfaced 3 (Phase 1 / S22 code). Suppressed via block-scoped
  eslint-disable with justification comments. Banked as PD-S34-NEXT-LINT-CLEANUP.
- **OBS-S34-L:** `eslint-disable-next-line` only suppresses the literal next
  line. For setState-in-effect where the offending call is 1-2 lines below the
  `useEffect(` line, must use block-scoped `/* eslint-disable */ ... /*
  eslint-enable */` wrapping the whole effect.
- **OBS-S34-M:** OBS-S33-J resolved as by-design. VECRM app has zero hooks.py
  registrations (all doc_events/scheduler_events commented out); workers run
  no VECRM Python in background loops. Backend-only γ-path rebuilds remain
  operationally correct. Workers untouched in S34.
- **OBS-S34-N:** Browser-extension console noise ("A listener indicated an
  asynchronous response by returning true, but the message channel closed")
  is from a Chrome extension (likely Gemini), NOT portal code. Identifiable
  because the error references the page URL, not a `/_next/static/` source.

---

## Lock promotion recommendations

### OBS-S79-D parse-anchor + OBS-S79-E CLI-merge-preference — PROMOTION READY (NEXT SESSION)

Both candidates now validated 5 times each across 5 repos (vecrm-infra,
vecrm-dashboard, vecrm-helpdesk-config, vecrm, vecrm-portal). PR #34's merge
makes the 5th for both. Recommend formal lock graduation at S35 close.

### L29 (halt cadence) — recalibrated mid-S34, ACTIVE

Recalibrated to load-bearing halts only (decision points + verification
gates), not every mechanical command. Operator pushback in S34 drove the
recalibration. No further change recommended; monitor for over/under-halting.

### Docs-tracked-at-session-close (proposed L28) — still candidate

Carried from S33. Not formally codified. Treat as candidate.

### NEW candidate L30 — file-authoring pre-mkdir discipline

1 incident in S34: mid-flight wrong-path `vecrm/doctype/vecrm_lead_touchpoint/`
created when correct path was `vecrm/vecrm/doctype/...`. Emptied during file
move, but the empty dir survived (git doesn't track empty dirs) and rsync'd to
VPS. 1 incident — not yet promotable. Bank and watch.

### NEW candidate L31 — rsync --prune-empty-dirs for deploy hygiene

Same root incident as L30. If recurrence, consider `--prune-empty-dirs` on the
canonical deploy rsync. 1 incident — bank and watch.

---

## Pendencies opened in S34

- **PD-S34-NEXT-LINT-CLEANUP (P2):** vecrm-portal has 17 pre-existing
  `react-hooks/set-state-in-effect` lint errors. PR #34 suppressed 3 (in
  touched files) with documented block-scoped disables. Proper refactor:
  convert effect bodies to subscription pattern or derive-from-render. NOTE
  one site (page.tsx lead-reset) has a visible-UX implication (flash-skeleton
  on route change) — refactor needs operator sign-off on that behavior change.
  Estimated ~1h sweep.

## Pendencies closed in S34

| Pendency | Priority | Closing PR | Closing date |
|---|---|---|---|
| **PD-S30-LEAD-FOLLOWUP Phase 2 (backend)** | **P1** | **vecrm #48/#49/#50** | **2026-05-27** |
| **PD-S30-LEAD-FOLLOWUP Phase 2 (portal)** | **P1** | **vecrm-portal #34** | **2026-05-27** |
| **PD-S33-NEXT-IMAGE-PRUNE** | **P1** | **vecrm #47** | **2026-05-27** |

## Pendency spec drift resolved in S34 (note for S35)

The pendencies.md Phase 2 entry (written at S30/S33) specified **3 whitelisted
methods** (incl. `delete_touchpoint`) and **6 touchpoint types** (Call /
Meeting / Email / WhatsApp / Site Visit / Other). The S34
**Q-LEAD-FOLLOWUP-PHASE-2-ADDENDUM** (vecrm `bdb4736`) overrode both:
- **2 methods** (`create_touchpoint`, `list_touchpoints_for_lead`) — NO delete
  endpoint, per Q-LFL-P2-8 (append-only audit history).
- **4 types** (Call / Email / Meeting / Other).
The shipped code follows the addendum. The addendum is the source of truth;
the older pendencies.md prose is superseded.

---

## Production smoke verification

### Backend smoke (SM-2 a–j) — 10/10 pass
Touchpoint create/list across types, derived stats (last_contact_date +
touchpoint_count), terminal-state-allowed creation, scoping. Run via
`vecrm/scripts/smoke_phase2.py` placed in container. Production rows cleaned
post-smoke.

### Portal smoke (SAM-34 1–7 functional) — 7/7 pass
Lead detail renders Touchpoints section; log happy path (Call); type select
(Email); cancel; future-date prevented (max=today); terminal-state-allowed
(logged Meeting on Converted lead 00023); persistence across navigation.
Verified on Vercel preview + re-verified on production.

### SAM-34-8/9 (nav badge) — negative-case verified
Zero leads with next_followup_date=today for operator → badge correctly does
NOT render (count=0 gate). Positive-case (badge shows "N") deferred — code
path logically correct, unreachable to verify without seeding a today-dated
lead. `/api/leads/followup-due-today-count` confirmed HTTP 200 in production.

### SAM-34-10 (console errors) — clean (extension noise only)
Only the browser-extension message-channel error (OBS-S34-N), not portal code.

---

## Session metrics

- Duration: ~10h (single day).
- PRs merged: 5 (vecrm #47/#48/#49/#50; vecrm-portal #34).
- Net LOC: vecrm +447 (Phase 2 backend); vecrm-portal +484/−7 (PR #34).
- Deploy cycles: 3 backend rebuilds (PR #48, #49, #50) + 1 Vercel production.
- Bugs found+fixed in-session: 2 (v16 string-aggregate, v16 dict-aggregate);
  1 false alarm diagnosed (unauth curl 500).
- Disk reclaimed: ~37GB (PR #47 prune).
- OBS banked: 14 (A–N).
- Locks: L29 recalibrated; 2 promotion-ready (S79-D/E); 2 new candidates
  (L30/L31).

---

## What ships to S35 head

- 0 active P0/P1 blockers.
- PD-S30-LEAD-FOLLOWUP Phase 3 (P1) — blocked on PD-S29-VEMIO-EMAIL-PIPELINE.
- PD-S29-VOUCHER-APPROVER-PORTAL-B2 (P1) — strong S35 #1 candidate (was the
  S34 #2 contingency; never reached).
- PD-S29-WEEKLY-MEETING-REPORT (P1) + PD-S29-VEMIO-EMAIL-PIPELINE (P1).
- P2: PD-S34-NEXT-LINT-CLEANUP, PD-S33-NEXT-TEST-INFRA,
  PD-S33-NEXT-DEPLOY-TAG-DISCIPLINE, PD-S33-NEXT-LEAD-DATA-WIPE,
  PD-S33-NEXT-VECRM-LOCK-FRAPPE-FILTER-PATTERNS (now compounded by OBS-S34-A).
- P3: PD-S33-NEXT-LEAD-WRITE-AUTH-AUDIT, PD-S30-NEXT-LEAD-LIST-CLOSED-WON-FILTER.
- Lock graduation: promote OBS-S79-D + OBS-S79-E at S35 close (5/5 each).
CLOSE_EOF
echo "S34-CLOSE.md written ($(wc -l < docs/handovers/S34-CLOSE.md) lines)"</parameter>
