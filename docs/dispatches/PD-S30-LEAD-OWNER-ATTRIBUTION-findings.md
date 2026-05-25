# PD-S30-LEAD-OWNER-ATTRIBUTION — Phase A recon findings

**Session:** S30 (authoring at S30 close); B-phase execution targeted for S31 open
**Recon branch:** `recon/s30-lead-owner-attribution` (vecrm repo; not pushed, awaiting operator review per VECRM discipline)
**Source dispatch:** `PD-S30-LEAD-OWNER-ATTRIBUTION-RECON-DISPATCH` (embedded in operator's prompt)
**Generated:** 2026-05-25
**Inheritance baselines:**
- vecrm `main = c808066` (PR #34 PIN policy tightening)
- vecrm-portal `main = 1d1218a` (PR #20 PinInput6Box ship) + PR #21 PinInput6Box visual polish open
- Active pendency: PD-S30-LEAD-OWNER-ATTRIBUTION (this recon's target)

---

## §0 — Headlines

**Bug confirmed real per OBS-S29-AAA 3-evidence-source threshold** (dispatch §2 evidence accepted; no contradicting source found).

**Root cause is a single line:** `vecrm/api.py:334` writes `doc.lead_owner = frappe.session.user`. Because all portal sessions authenticate as the shared service account `vecrm-portal@vinayenterprises.co.in` (per VECRM-LOCK-PORTAL-SHARED-PRINCIPAL), `frappe.session.user` is always the service account — never the human.

**Bug surface is wider than the headline:** 4 of 6 `frappe.session.user` references write to user-visible-attribution fields. 2 are correct-for-purpose (Frappe counter-table metadata). The Inquiry inherits the bug via cascade at `vecrm_lead.py:160`.

**Critical dispatch correction (§H below):** the dispatch §R9 claim "scoping returns zero rows for every Sales Rep" is **WRONG**. Per-rep scoping (`lib/scoping.ts`) filters on `creating_employee` (the S27 PR #20 substrate), NOT `lead_owner`. `creating_employee` is correctly set at `api.py:340` (one line below the bug). Scoping is NOT broken. The P1 priority still holds — but on the basis of the follow-up workflow blocker + email-to-rep recipient + audit forensics, not the scoping concern.

**Fix surface is small:** single-line change in `create_lead`, single-line change in `vecrm_lead.py before_save`, 2 single-line changes in voucher_*.py audit-payload assignments. Migration is one-shot UPDATE per doctype (conditional on operator probe of FK constraint — see §F).

**No new helper needed for fix:** `frappe.session.data.get("vecrm_employee_phone")` is the established mechanism (S25 pattern; 9 existing call sites in api.py); resolving to `vecrm_email` is one extra DB lookup. Recommend extending `_issue_session` to also stash `vecrm_email` to avoid the lookup on every write (~2 line addition).

---

## §A — `frappe.session.user` reference catalog (R1)

**6 references across 5 files. Classification:**

| # | File:line | Code | Use | Classification |
|---|-----------|------|-----|----------------|
| 1 | `vecrm/api.py:334` | `doc.lead_owner = frappe.session.user` | Lead user-facing attribution | **WRONG (attribution)** — root cause of headline bug |
| 2 | `vecrm/vecrm/voucher_counter.py:185` | `usr = frappe.session.user` → INSERT `owner` + `modified_by` on `tabVECRM Voucher Counter` | Frappe row-metadata on counter table | **CORRECT-ish (convention)** — counter is incremented by both portal AND Desk admin; `frappe.session.user` is the Frappe-canonical "request initiator" value for `owner`/`modified_by`. Not user-visible; rarely consulted. Banking as low-priority candidate cleanup. |
| 3 | `vecrm/vecrm/voucher_counter.py:247` | Same on UPDATE `modified_by` | Counter row metadata | **CORRECT-ish** — same as #2 |
| 4 | `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py:206` | `"actor_user": frappe.session.user` in VECRM Voucher Audit Log payload | Voucher audit identifier | **WRONG (audit identifier)** — should be human's vecrm_email or VECRM Employee PK; currently records BFF service account on every voucher state-change event |
| 5 | `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:162` | Same | Voucher audit identifier | **WRONG (audit identifier)** — same as #4 |
| 6 | `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py:84` | `actor = frappe.session.user` → used for `changed_by` in reassignment_history child row + VECRM Assignment Ledger Entry | Owner-change ledger | **WRONG (attribution)** — should be the human who actually changed the owner |

**Score: 4 wrong, 2 correct-ish.** The 2 correct-ish are Frappe-convention row metadata that's invisible to end users; leave alone or fix in a future hygiene pass.

**Adjacent context — `frappe.session.data.get(...)` references: 16.** All correctly read the per-session VECRM identity (`vecrm_employee_phone`, `vecrm_employee_role`, `vecrm_login_path`). The session-data mechanism IS the correct identity-resolution channel; it just isn't being used at site #1 / #6 for attribution.

---

## §B — `*_owner` write-path catalog (R2)

**Lead `lead_owner` write sites: 1 (the headline bug).**

| File:line | Code | Comment |
|---|---|---|
| `vecrm/api.py:334` | `doc.lead_owner = frappe.session.user` | The bug. |

**Inquiry `inquiry_owner` write sites: 1 (cascade from Lead).**

| File:line | Code | Comment |
|---|---|---|
| `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py:160` | `"inquiry_owner": self.lead_owner` (inside `convert_to_inquiry`) | Inherits whatever Lead's owner is. Cascade — fix Lead, Inquiry follows. |

**Other owner-like writes:**

| File:line | Code | Comment |
|---|---|---|
| `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py:99-100, 109-110` | `from_owner: before.lead_owner` + `to_owner: self.lead_owner` (in reassignment_history child + Assignment Ledger Entry) | Records the from/to of an owner change. NOT a NEW attribution; just records the existing values. The bug it carries is that pre-fix Leads' `lead_owner` was always the service account, so ledger entries say "from=vecrm-portal to=vecrm-portal" which conveys no information. |

**Field types (per doctype JSON probes):**

| Field | Doctype | Type | Target |
|---|---|---|---|
| `lead_owner` | VECRM Lead | `Link` | `User` (Frappe User, email-keyed) |
| `inquiry_owner` | VECRM Inquiry | `Link` | `User` |
| `creating_employee` | VECRM Lead | `Link` | `VECRM Employee` (phone-keyed) |
| `submitter` | VECRM Travel Voucher | `Link` | `VECRM Employee` (phone-keyed) |
| `submitter` | VECRM Expense Voucher | `Link` | `VECRM Employee` (phone-keyed) |
| `changed_by` | VECRM Assignment Ledger Entry | `Data` (free-form string) | n/a |

**Architectural observation:** Lead/Inquiry use `Link → User` (Frappe email-keyed) for owner. Vouchers use `Link → VECRM Employee` (phone-keyed) for submitter. Different conventions. The fix for `lead_owner` must write a **valid Frappe User name** (i.e., the human's `vecrm_email`), not a phone. This raises the FK question in §F.

---

## §C — Human-identity resolution mechanisms available to backend (R3)

**Existing mechanism (the canonical one — S25 PR #16 era):**

```python
employee_phone = frappe.session.data.get("vecrm_employee_phone")
```

Set by `_issue_session` at login (api.py:536). Read at 9 sites in api.py:
- `create_lead` line 340 (`creating_employee` field — CORRECT)
- `vecrm_logout` line 704
- `get_session_employee` line 718
- `change_password` line 1271
- `change_pin` line 1374
- Several reset-flow paths

**The bug at api.py:334 is that the line BELOW (340) already reads the correct value for `creating_employee`. The two-line block:**

```python
doc.lead_owner = frappe.session.user                                      # line 334 — WRONG
doc.creating_employee = frappe.session.data.get("vecrm_employee_phone")   # line 340 — CORRECT
```

Same context, same session, same access — but two different identity sources. The bug is the choice at line 334, not a missing mechanism.

**What `_issue_session` stashes (line 536-539):**
- `vecrm_employee_phone` ✓ (used everywhere)
- `vecrm_employee_name` ✓ (display name "Ajay Salvi")
- `vecrm_employee_role` ✓
- `vecrm_login_path` ✓
- **`vecrm_email` is NOT stashed** — backend must DB-lookup if it wants the email

**Helper opportunity:** to fix `lead_owner = <human vecrm_email>`, the fastest path is one of:

| Option | Mechanism | Cost |
|---|---|---|
| **(a)** | DB lookup per call: `frappe.db.get_value("VECRM Employee", phone, "vecrm_email")` | 1 extra DB query per Lead create |
| **(b)** | Extend `_issue_session` to also stash `vecrm_email` in session data; backend reads `frappe.session.data.get("vecrm_email")` directly | 2 lines added to `_issue_session`; zero per-request lookup. **Recommended.** |

**No `_resolve_real_user_from_request()` helper exists today.** Could be authored but unnecessary — Option (b) with `frappe.session.data.get("vecrm_email")` IS the helper; just shorter and inline.

**`frappe.request` / `frappe.get_request_header` usage in api.py:** 1 site (line 416, `User-Agent` for audit logging). No cookie-reading code path in vecrm backend — Frappe's session middleware handles cookie parsing before the request reaches whitelist methods.

---

## §D — Audit log identifier audit (R4)

**`_audit_auth` family (auth events) — 20+ call sites — all CORRECT:**

Consistent pattern:
- `identifier=email` or `identifier=phone` — when pre-lookup (login attempt with unknown identifier)
- `employee=employee_doc.name` (phone PK) — when post-lookup (identity resolved)

Examples:
- `_audit_auth("auth.login.success", employee=employee_doc.name, path="password")` — correct
- `_audit_auth("auth.login.failed", identifier=email, path="password", reason="missing_input")` — correct (email here is the SUBMITTED string, not session identity)

The auth-audit-reason taxonomy (now 11 values post-PR #34) is internally consistent. **No bug surface in `_audit_*` family.**

**Voucher Audit Log (`VECRM Voucher Audit Log` doctype):**

Travel + Expense Voucher controllers emit audit rows with:
```python
merged_payload = {
    "voucher_name": self.name,
    "voucher_doctype": self.doctype,
    "actor_user": frappe.session.user,    # ← WRONG (sites #4, #5 in §A)
}
```

`actor_user` records the BFF service account on every voucher state-change event. Historical voucher audit rows in production carry `actor_user=vecrm-portal@vinayenterprises.co.in` — wrong, but those rows aren't yet user-facing because voucher workflow hasn't shipped to general users (only the test rep has voucher rows in production, if any).

**Assignment Ledger Entry / Assignment Log Row:**

`changed_by` field is `Data` (free-form string), populated by `vecrm_lead.py:84` via `actor = frappe.session.user` (site #6 in §A). Currently every ledger row would say "vecrm-portal@..." changed the owner. But: pre-fix, no Lead has ever had its owner changed (creates always set `lead_owner = vecrm-portal@...`; no human user-action would change it because the UI doesn't expose lead_owner edit). So in practice, **zero existing ledger rows** for owner changes. The bug exists but hasn't fired in production.

---

## §E — Portal BFF call paths (R5)

### §E.1 — Lead BFF (`app/api/leads/route.ts:89-` POST handler)

The Lead create flow:
1. Browser POST `/api/leads` with form fields
2. BFF reads `cookie = req.headers.get("cookie")` (the SID for the shared portal user)
3. BFF forwards body keys (`company_name, territory, contact_date, priority, contact_number, contact_email, meeting_brief`) to `vecrm.api.create_lead`
4. Backend `create_lead` runs with `frappe.session.user = "vecrm-portal@..."`

**Notable: the BFF does NOT pass the human's identity to backend.** It only forwards the cookie. The backend's `frappe.session.data.get("vecrm_employee_phone")` works because the session data was stashed at login time — not because the BFF passed it through.

### §E.2 — Convert BFF (`app/api/leads/[name]/convert/route.ts`)

Calls `vecrm.api.convert_lead_to_inquiry`. Backend method calls `lead.convert_to_inquiry(...)` (the Lead controller method) which sets `inquiry_owner: self.lead_owner` — cascade bug surface.

### §E.3 — Travel Voucher BFF (`app/api/travel-vouchers/route.ts`)

**Different pattern — explicit user-identity param:**

```ts
interface CreateBody {
  submitter: string; // Sub-A: Admin picks; S25: resolved from session
  // ...
}
// ...
body: {
  submitter: body.submitter,    // ← browser passes; BFF relays
  // ...
}
```

Backend `create_travel_voucher_draft(submitter, ...)` REQUIRES `submitter` as explicit param + validates `frappe.db.exists("VECRM Employee", submitter)`.

This is the **correct attribution pattern** — explicit param, backend-validated. Lead got it WRONG; Travel Voucher got it RIGHT.

**Latent gap in Travel Voucher BFF:** the browser passes `submitter` directly. The BFF does NOT derive it from session — it trusts the browser-supplied value. The original Sub-A (S24) shipped with this gap because S25 auth hadn't shipped yet. Per the inline comment "S25: resolved from session" — this BFF integration was never completed. **Worth banking as OBS-S30-EE for follow-up** (out of scope per dispatch §6 voucher-related items).

### §E.4 — `getVecrmSession` is server-only and unused by BFFs

`lib/auth-ssr.ts:getVecrmSession()` returns `{employee, name, role, vecrm_email, base_city, login_path}` (extended in S29 PR #18). It is currently used ONLY by:
- Page-level server components (`app/account/page.tsx` etc.)
- `lib/scoping.ts` (via `getScopedLeadFilter` + `canReadLead`)

**No BFF route currently imports `getVecrmSession`.** Grep confirms.

**Implication for fix:** the portal BFF COULD read `vecrm_email` via `getVecrmSession()` and pass it as an explicit param to backend `create_lead`. This would mirror the Travel Voucher pattern. But it's REDUNDANT — the backend already has the session-data access. Simpler fix: backend uses what's already in session. (See §I.1.)

---

## §F — Migration scope for existing 15 Leads + 13 Inquiries (R6)

### §F.1 — Operator probes (to run before B-phase)

Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS — Code authors, operator runs.

```bash
# F-1.1 — Current attribution distribution on Lead
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT lead_owner, COUNT(*) AS rows FROM \`tabVECRM Lead\` GROUP BY lead_owner"'
# Expected (per dispatch evidence): all rows have lead_owner = vecrm-portal@vinayenterprises.co.in

# F-1.2 — Current attribution distribution on Inquiry
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT inquiry_owner, COUNT(*) AS rows FROM \`tabVECRM Inquiry\` GROUP BY inquiry_owner"'

# F-1.3 — Row counts (sanity vs dispatch's 15/13 claim)
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT (SELECT COUNT(*) FROM \`tabVECRM Lead\`) AS leads, (SELECT COUNT(*) FROM \`tabVECRM Inquiry\`) AS inquiries"'

# F-1.4 — CRITICAL: does ajay@vinayenterprises.co.in exist as a Frappe User? (FK constraint check for migration target)
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT name, enabled, user_type FROM \`tabUser\` WHERE name = \"ajay@vinayenterprises.co.in\""'
# IF EMPTY: lead_owner = Link → User FK constraint will REJECT the migration UPDATE.
#   Mitigation: create the Frappe User row as part of the migration patch (Website User type, no portal access — exists only to satisfy FK and carry the email identifier)
# IF PRESENT: migration UPDATE is a one-line UPDATE per doctype, no FK issue.

# F-1.5 — Cross-reference: ajay@vinayenterprises.co.in is the vecrm_email of which VECRM Employee?
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT name, employee_name, vecrm_email FROM \`tabVECRM Employee\` WHERE vecrm_email = \"ajay@vinayenterprises.co.in\""'
# Expected: 1 row, name = +91-9327547536, employee_name = Ajay Salvi
```

### §F.2 — Migration patch shape (conditional on F-1.4 result)

**Case A — Frappe User exists:** one-line UPDATE per doctype.

```python
# vecrm/patches/v1_4/migrate_lead_owner_attribution.py
def execute():
    frappe.db.sql("""
        UPDATE `tabVECRM Lead`
        SET lead_owner = 'ajay@vinayenterprises.co.in'
        WHERE lead_owner = 'vecrm-portal@vinayenterprises.co.in'
    """)
    frappe.db.sql("""
        UPDATE `tabVECRM Inquiry`
        SET inquiry_owner = 'ajay@vinayenterprises.co.in'
        WHERE inquiry_owner = 'vecrm-portal@vinayenterprises.co.in'
    """)
    frappe.db.commit()
```

**Case B — Frappe User does NOT exist:** create User first, then UPDATE.

```python
def execute():
    if not frappe.db.exists("User", "ajay@vinayenterprises.co.in"):
        user = frappe.new_doc("User")
        user.email = "ajay@vinayenterprises.co.in"
        user.first_name = "Ajay"
        user.last_name = "Salvi"
        user.user_type = "Website User"  # NOT System User; no Desk access
        user.enabled = 1
        user.send_welcome_email = 0
        user.insert(ignore_permissions=True)
    # Then same UPDATEs as Case A
```

### §F.3 — Rollback patch (always paired per VECRM-L22)

```python
# vecrm/patches/v1_4/rollback_migrate_lead_owner_attribution.py
def execute():
    frappe.db.sql("""
        UPDATE `tabVECRM Lead`
        SET lead_owner = 'vecrm-portal@vinayenterprises.co.in'
        WHERE lead_owner = 'ajay@vinayenterprises.co.in'
    """)
    frappe.db.sql("""
        UPDATE `tabVECRM Inquiry`
        SET inquiry_owner = 'vecrm-portal@vinayenterprises.co.in'
        WHERE inquiry_owner = 'ajay@vinayenterprises.co.in'
    """)
    frappe.db.commit()
    # NOTE: if Case B created a Frappe User in the forward patch, the
    # rollback does NOT remove it (deleting a User row has cascading
    # FK implications; safe to leave the row in place — harmless if
    # disabled).
```

### §F.4 — Multi-rep risk

The dispatch claims "only Ajay has portal-submitted Leads" — verified by:
1. F-1.5 probe shows Ajay is the only VECRM Employee with `vecrm_email = ajay@vinayenterprises.co.in`
2. Test Sales Rep (+91-9999900001) + Test HR Approver (+91-9999900002) exist as fixtures but have not actively created Leads (per S30 close pendency: zero non-Ajay portal-submitted activity)

**If F-1.1/F-1.2 surface any rows with non-`vecrm-portal@...` owners, OR if the operator recalls any Test* fixture activity, the migration is NON-trivial** and would need creation-timestamp + audit-log cross-reference per row. Recon recommends running F-1.1 / F-1.2 first to verify the one-shot assumption.

### §F.5 — Audit log migration: AMNESTY (do not migrate)

- VECRM Voucher Audit Log: rows pre-fix carry `actor_user=vecrm-portal@...`. These are HISTORICAL TRUTH — at the time of the event, the BFF was the actor we recorded. Don't rewrite history.
- VECRM Assignment Ledger Entry / Assignment Log Row: zero pre-fix rows expected (no owner-change UI shipped). Verify via F-1.6 below; if zero, no migration needed.
- VECRM Auth Audit Log: already correct (uses phone PK).

```bash
# F-1.6 — Confirm zero pre-fix Assignment Ledger Entry rows
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT COUNT(*) FROM \`tabVECRM Assignment Ledger Entry\`"'
# Expected: 0
```

---

## §G — Adjacent attribution surfaces (R7)

| Doctype | Field | Current attribution | Bug? |
|---|---|---|---|
| VECRM Lead | `lead_owner` (Link → User) | `frappe.session.user` (service account) | **WRONG** — fix in api.py:334 |
| VECRM Lead | `creating_employee` (Link → VECRM Employee) | `frappe.session.data.vecrm_employee_phone` (correct human phone) | OK |
| VECRM Inquiry | `inquiry_owner` (Link → User) | cascades from `self.lead_owner` | WRONG via cascade — fixes itself once Lead fix lands |
| VECRM Travel Voucher | `submitter` (Link → VECRM Employee) | explicit API param, backend-validated | OK (architecturally correct; BFF latent gap noted in §E.3) |
| VECRM Expense Voucher | `submitter` (Link → VECRM Employee) | same as Travel Voucher | OK (same caveat) |
| VECRM Voucher Audit Log | `payload.actor_user` (JSON field) | `frappe.session.user` | **WRONG** — fix in vecrm_travel_voucher.py:206 + vecrm_expense_voucher.py:162 |
| VECRM Assignment Ledger Entry | `changed_by` (Data) | `frappe.session.user` via vecrm_lead.py:84 | **WRONG** — fix in vecrm_lead.py:84 |
| VECRM Assignment Log Row (child) | `changed_by` (Data) | same as above | WRONG (same root) |
| VECRM Auth Audit Log | `employee` (Link) | phone PK from various sources | OK (already correct per S29 PR #29 pattern) |
| VECRM Voucher Counter | Frappe `owner` / `modified_by` metadata | `frappe.session.user` | OK-ish (Frappe convention for row metadata; not user-visible) |

**Adjacent doctype probes (operator-runs):**

```bash
# G-1.1 — Travel Voucher submitter distribution (sanity)
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT submitter, COUNT(*) FROM \`tabVECRM Travel Voucher\` GROUP BY submitter"'

# G-1.2 — Expense Voucher submitter distribution
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT submitter, COUNT(*) FROM \`tabVECRM Expense Voucher\` GROUP BY submitter"'

# G-1.3 — Voucher Audit Log payload sample (confirm actor_user value)
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT JSON_EXTRACT(payload, \"\$.actor_user\") AS actor, COUNT(*) FROM \`tabVECRM Voucher Audit Log\` GROUP BY actor"'
```

---

## §H — Coupling with deferred pendency items (R8 + R9)

### §H.1 — PD-S30-LEAD-FOLLOWUP-WORKFLOW (R8 — coupling CORRECT)

The follow-up reminder workflow requires email to the human Lead owner. Currently `lead_owner = vecrm-portal@...` → emails go to a service-account inbox nobody checks. **Workflow is unusable until LEAD-OWNER-ATTRIBUTION ships.** Coupling confirmed.

### §H.2 — Per-rep scoping (R9 — DISPATCH CLAIM INCORRECT)

**The dispatch's §R9 claim is WRONG.** Per `vecrm-portal/lib/scoping.ts:38-41`:

```ts
export async function getScopedLeadFilter(): Promise<
  ["creating_employee", "=", string] | null
> {
  // ...
  return ["creating_employee", "=", session.employee];
}
```

The scoping filter is `["creating_employee", "=", "<phone>"]`, **NOT** `["lead_owner", "=", "<email>"]`. `creating_employee` is the S27 PR #20 substrate field at `Lead` doctype JSON, populated at `api.py:340` from `frappe.session.data.get("vecrm_employee_phone")` (correctly).

**Implication:** scoping works correctly for Lead today. A non-Admin Sales Rep would see only their own Leads (those with their phone in `creating_employee`). The bug in `lead_owner` is a user-visible display + email-to-owner blocker, NOT a scoping blocker.

**Inquiry caveat:** Inquiry scoping doesn't exist yet (S29 PR #16 was Lead-only). When Inquiry scoping ships, it would use `inquiry_owner` (which inherits the bug) — at that point the cascade matters. But Inquiry doesn't have a `creating_employee` substrate, so a future Inquiry-scoping PR would need to either (a) add `creating_employee` to Inquiry, OR (b) use `inquiry_owner` (which the LEAD-OWNER-ATTRIBUTION fix makes correct going forward).

**P1 priority still justified** on the basis of:
- User-visible UI bug ("Lead Owner: vecrm-portal@..." on every Lead)
- Email-to-rep recipient (follow-up workflow blocker per §H.1)
- Audit forensics (Voucher Audit Log `actor_user` records wrong identity)
- Inquiry scoping when it ships (future blocker)

**P1 NOT justified on the basis of:**
- ~~"Sales Reps see zero Leads"~~ — dispatch §R9 claim incorrect; scoping works via `creating_employee`

---

## §I — Proposed Phase B shape

### §I.1 — Recommended PR structure: 2 PRs

| PR | Repo | Branch | Scope |
|---|---|---|---|
| **PR-1 (backend code fix)** | vecrm | `fix/s31-lead-owner-attribution-code` | (1) extend `_issue_session` to stash `vecrm_email`; (2) fix `api.py:334` `lead_owner` source; (3) fix `vecrm_lead.py:84` `actor` source; (4) fix voucher_travel.py:206 + voucher_expense.py:162 `actor_user` source. ~10 lines of behavioral change + docstring updates. |
| **PR-2 (migration patch)** | vecrm | `fix/s31-lead-owner-attribution-migrate` | (5) v1_4 forward + rollback patches; (6) patches.txt registration. **Conditional Case A vs Case B based on F-1.4 probe result** — operator runs probe before authoring this PR. |

**Why 2 PRs not 1:**
- Code fix is forward-only (no schema change; no data migration). Can ship + deploy + smoke standalone — new Leads created post-deploy carry correct `lead_owner`.
- Migration patch is a one-off data rewrite. Ships separately so the code-fix smoke can prove the forward path works BEFORE we touch existing data. If migration fails (e.g., FK constraint surprise), code fix stays in place; pending-migration Leads continue to be createable correctly.

**Merge order:** PR-1 backend → deploy + smoke (verify new Leads attribute correctly) → PR-2 migration → smoke (verify existing 15+13 rows updated). Same pattern as S29 PR #29 (write-pattern fix) → operator bootstrap (Ajay's PIN).

### §I.2 — Files touched

**PR-1:**

| File | Change | Lines |
|---|---|---|
| `vecrm/api.py` | (a) `_issue_session` stash `vecrm_email`; (b) line 334 `lead_owner` source change | ~6 |
| `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.py` | line 84 `actor` source change | ~2 |
| `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py` | line 206 `actor_user` source | ~2 |
| `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py` | line 162 `actor_user` source | ~2 |

**PR-2:**

| File | Change |
|---|---|
| `vecrm/patches/v1_4/__init__.py` | NEW (package marker) |
| `vecrm/patches/v1_4/migrate_lead_owner_attribution.py` | NEW (forward, conditional Case A/B per F-1.4) |
| `vecrm/patches/v1_4/rollback_migrate_lead_owner_attribution.py` | NEW (paired rollback per L22) |
| `vecrm/patches.txt` | Register forward |

### §I.3 — Smoke matrix

**PR-1 backend smokes (operator-driven via curl + browser):**

| # | Test | Expected |
|---|------|----------|
| LOA-1 | Operator logs in via portal → creates new Lead via UI | New Lead's `lead_owner` field shows `ajay@vinayenterprises.co.in` (NOT `vecrm-portal@...`) |
| LOA-2 | Same — verify backend via curl `frappe.client.get_value("VECRM Lead", "<name>", "lead_owner")` | Returns `ajay@vinayenterprises.co.in` |
| LOA-3 | Operator converts the LOA-1 Lead to Inquiry | New Inquiry's `inquiry_owner` = `ajay@vinayenterprises.co.in` (cascade works) |
| LOA-4 | Browser: `/leads/<name>` and `/inquiries/<name>` detail pages | UI shows "Lead Owner: ajay@vinayenterprises.co.in" |
| LOA-5 | Operator's session continues working (no session-data corruption from `_issue_session` extension) | Login + logout + change_password + change_pin all still function |
| LOA-6 (regression) | New Lead's `creating_employee` field unchanged | Still `+91-9327547536` (phone) — proves the existing correct field wasn't disturbed |
| LOA-7 (regression) | Scoping still works | Per-rep scoping test from S29 PR #16: scoped reads return owned Leads |

**PR-2 migration smokes:**

| # | Test | Expected |
|---|------|----------|
| LOA-M1 | Pre-migration count: `SELECT COUNT(*) FROM tabVECRM Lead WHERE lead_owner = 'vecrm-portal@...'` | 15 (or current count from F-1.1) |
| LOA-M2 | Run `bench migrate` | Patch v1_4 lands; logs show "<N> Lead rows migrated, <M> Inquiry rows migrated" |
| LOA-M3 | Post-migration count: same query | 0 |
| LOA-M4 | Post-migration count: `SELECT COUNT(*) FROM tabVECRM Lead WHERE lead_owner = 'ajay@vinayenterprises.co.in'` | 15 |
| LOA-M5 | Browser: open any pre-S30-fix Lead detail page | UI shows "Lead Owner: ajay@vinayenterprises.co.in" |
| LOA-M6 | Rollback patch executable (dry-run on local dev): rollback restores `vecrm-portal@...` | Verified before deploying forward |

### §I.4 — Rollback

PR-1: standard `git revert` + redeploy via PD-S27-DEPLOY-RUNBOOK; new Leads return to buggy attribution; no data corruption.

PR-2: run `vecrm.patches.v1_4.rollback_migrate_lead_owner_attribution.execute` (manually via `bench execute`); restores `lead_owner = vecrm-portal@...` on the affected 15+13 rows. If Case B created a Frappe User for Ajay, the rollback does NOT remove it (deletion has cascading FK risk).

---

## §J — Open questions for dispatcher review (ATT-1 through ATT-12)

### Architecture

**ATT-1.** **Final decision: pass `acting_user_email` as explicit API param, or use backend session-data read?**
- Recon recommends **session-data read** (Option (b) from §C). Simpler — no portal change needed. Backend pulls `vecrm_email` from session data, which `_issue_session` already maintains.
- Explicit param would mirror Travel Voucher's pattern but adds 2-side coordination (backend signature + portal BFF) for no functional benefit (BFF and backend share the same session cookie's session data already).

**ATT-2.** **Where does the portal BFF currently read `vecrm_email` from?**
- Lead BFF: NOWHERE (the bug)
- Travel Voucher BFF: doesn't read either; relays browser-supplied value
- `getVecrmSession()` (lib/auth-ssr.ts) does the lookup via backend `get_session_employee` — used by pages, not BFFs
- **Recon recommendation:** no portal change needed. Backend pulls from its own session data.

**ATT-3.** **Is there an existing `_resolve_real_user_from_request()` helper?**
- NO. Recommend NOT authoring one — `frappe.session.data.get("vecrm_email")` is the inline-helper. Adding a wrapper function over a single dict lookup is over-engineering.
- IF `_issue_session` is extended per §C Option (b), backend code becomes: `doc.lead_owner = frappe.session.data.get("vecrm_email")`. 1 line.

### Validation

**ATT-4.** **Should backend reject calls missing the human identity, or fall back?**
- Recommend **reject loud**. If session data lacks `vecrm_email`, that's a session-state bug worth surfacing. `frappe.throw("VECRM session missing vecrm_email", frappe.SessionStopped)` or similar. NO silent fallback to `frappe.session.user`.
- Falling back to service account would re-introduce the bug class. Rejecting forces the operator to fix any session-state issue immediately.

**ATT-5.** **Should `vecrm-portal@vinayenterprises.co.in` ever be a valid `lead_owner` value?**
- Recommend **no**. Add an assertion in `create_lead`: `if doc.lead_owner == "vecrm-portal@vinayenterprises.co.in": frappe.throw(...)`. Belt-and-braces against future re-introduction.
- Desk-side admin Lead creation (rare) would set `lead_owner` to whatever Frappe User did the create (probably `Administrator` or `<operator's Frappe User name>`). Both are non-service-account; the assertion only catches the bug class.

### Surface scope

**ATT-6.** **Full list of API/code sites needing the fix:**

1. `api.py:334` — `create_lead`'s `lead_owner` write
2. `vecrm_lead.py:84` — `before_save` `actor` for reassignment ledger
3. `vecrm_travel_voucher.py:206` — Voucher Audit Log `actor_user`
4. `vecrm_expense_voucher.py:162` — Voucher Audit Log `actor_user`
5. `api.py` `_issue_session` (line 520+) — extend to stash `vecrm_email` (foundation for all above)

**Total: 5 surgical edits in 4 files.**

**Out of fix scope:**
- `voucher_counter.py:185, 247` — Frappe row-metadata convention; acceptable as-is. Banking as OBS-S30-FF for future cleanup.

**ATT-7.** **Adjacent doctypes' attribution fields confirmed:**
- Travel Voucher `submitter`: already correct architecture (explicit param + backend validation). Latent BFF-derive-from-session gap noted as OBS-S30-EE; out of LOA-fix scope.
- Expense Voucher `submitter`: same.
- Sales Visit doctype: doesn't exist yet (Session-0 backlog item).
- Frappe HD ticket creation: VECRM doesn't create HD tickets (verified via grep).

### Migration

**ATT-8.** **Migrate existing 15 Leads + 13 Inquiries?**
- Recommend **YES**. The migration is trivial (one-shot UPDATE per doctype), reversible (paired rollback per L22), and removes the user-visible UI bug from all existing rows (operator sees "Lead Owner: ajay@..." on every Lead they open after deploy, not just newly-created ones).
- Amnesty-forward alternative: existing rows continue to show `vecrm-portal@...`. Operationally noisy; operator would see two flavors of Lead.

**ATT-9.** **Migrate audit log rows?**
- Recommend **NO** for VECRM Voucher Audit Log (historical truth — even "wrong" identity is what was recorded; don't rewrite history).
- Per §F.5, VECRM Assignment Ledger Entry has zero pre-fix rows (operator probe F-1.6 confirms). No migration target.
- VECRM Auth Audit Log: already correct; no migration needed.

**ATT-10.** **Migration: one-shot UPDATE per doctype, or per-row with creation-timestamp reconciliation?**
- Recommend **one-shot UPDATE** conditional on operator probes F-1.1, F-1.2, F-1.4 surfacing the expected uniform state ("all rows currently `vecrm-portal@...`; only Ajay is the candidate target; Frappe User exists OR can be created").
- If any probe surfaces multi-rep activity (unlikely), per-row reconciliation needed. Recon strongly suggests probing FIRST.

### Coupling

**ATT-11.** **PD-S30-LEAD-FOLLOWUP-WORKFLOW dependency:**
- **CONFIRMED.** Follow-up workflow requires correct `lead_owner` for email recipient. LOA fix is a prerequisite.

**ATT-12.** **Per-rep scoping (S29 PR #16) status post-fix:**
- **NO CHANGE NEEDED.** Scoping uses `creating_employee`, not `lead_owner`. Already correct. **Dispatch §R9 claim corrected here in §H.2.**
- Future Inquiry scoping (when authored) will benefit from the cascade fix — `inquiry_owner` becomes a usable scoping field.

### Newly surfaced

**ATT-13.** **Operator probe F-1.4 (Frappe User existence) is a P0 BLOCKER for PR-2.** If `ajay@vinayenterprises.co.in` doesn't exist as a Frappe User, the migration UPDATE will FAIL via FK constraint. Case B (create User first) requires operator decision on Website User type vs System User type. Recommend Website User (no Desk access; exists only for FK + identifier carry).

**ATT-14.** **Voucher Audit Log `actor_user` payload migration: explicitly NO** per ATT-9 (historical truth). But the FIX to `actor_user` going forward is part of PR-1 (sites #4, #5 in §A).

### OBS-S30 observations banked

- **OBS-S30-EE** — Travel Voucher + Expense Voucher BFFs relay browser-supplied `submitter` instead of deriving from session. Latent gap; the trust boundary is currently the browser (a malicious portal client could submit a voucher attributed to a different employee). Out of LEAD-OWNER-ATTRIBUTION scope; revisit at voucher workflow design.
- **OBS-S30-FF** — `voucher_counter.py:185, 247` use `frappe.session.user` for row metadata. Frappe convention; not user-visible. Banking as low-priority cleanup if a future audit pass surfaces it as an issue.
- **OBS-S30-GG** — Dispatch §R9 claim about scoping was incorrect. Scoping uses `creating_employee`, not `lead_owner`. Recon corrects in §H.2. Worth a brief addendum to S29 PR #16 documentation if/when revisited (the recon-findings doc for S29 Workstream A may benefit from this clarification).

---

## §K — References

- Source dispatch: PD-S30-LEAD-OWNER-ATTRIBUTION-RECON-DISPATCH (embedded in operator's prompt)
- Bug-establishing evidence (per OBS-S29-AAA): dispatch §2
- Backend (vecrm): main `c808066` (PR #34 PIN policy)
- Portal (vecrm-portal): main `1d1218a` (PR #20 PinInput6Box ship); PR #21 visual polish open
- Architectural lock: VECRM-LOCK-PORTAL-SHARED-PRINCIPAL (S27) — established the BFF service-account model that this bug stems from
- S25 session-data pattern: `_issue_session` at `vecrm/api.py:520+`
- S27 PR #20: `creating_employee` substrate (the CORRECT field that scoping uses)
- S29 PR #16: `lib/scoping.ts` (uses `creating_employee`, not `lead_owner`)
- S29 PR #18: `vecrm_email` added to `get_session_employee` response (foundation for `getVecrmSession` portal helper)
- S29 PR #29: auth-write-pattern fix — established the canonical `passlibctx.hash + frappe.db.set_value` pattern; relevant context for this recon's parallel "wrong identity-source" bug class
