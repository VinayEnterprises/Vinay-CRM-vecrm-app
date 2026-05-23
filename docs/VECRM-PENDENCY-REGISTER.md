# VECRM-PENDENCY-REGISTER

**Last regenerated:** S25 close, 23 May 2026
**Maintained by:** Session-close handovers (per VECRM-L2 — decisions written, not remembered)
**Scope:** Active backlog, strategic priorities, infrastructure debt, known schema drift, out-of-scope clarifications.

This register is **regenerated comprehensively at every session close**. Surgical edits between session closes are acceptable for adding/closing individual PDs but the register is fully reviewed and regenerated at session boundaries.

---

## PART A — Tactical pendencies (active backlog, S26)

### Highest priority — Auth backlog (the natural S26 frontier)

These items are the direct continuation of S25's PD-S25-VECRM-AUTH v2.

#### PD-S26-AUTH-PHONE-PIN — Phone+PIN backend (companion to email+password)

**Estimated:** 4-6 hours
**Scope:**
- Add `pin_hash` (Data fieldtype, NOT Password — per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE), `failed_pin_attempts`, `pin_locked_until`, `last_pin_login_at` fields to VECRM Employee
- New whitelisted endpoint `vecrm.api.login_with_pin(phone: str, pin: str)`
- Same lockout (5/15min), audit emission, generic 401 mechanics as email+password
- Update `_issue_session` to set `login_path: "pin"` instead of `"password"`
- Migration patch + paired rollback

**Why this is priority 1 for S26:** Field reps will use phones; PIN entry is faster than email+password on mobile.

#### PD-S26-AUTH-RESET — Email-based password reset flow

**Estimated:** 6-10 hours
**Scope:**
- New doctype `VECRM Auth Reset Token`: token (Data, unique), employee (Link), expires_at (Datetime), used_at (Datetime, nullable)
- New whitelisted endpoint `vecrm.api.request_password_reset(email: str)` — issues token, sends email via Microsoft Graph
- New whitelisted endpoint `vecrm.api.complete_password_reset(token: str, new_password: str)` — validates token + TTL + not-used, sets password
- Rate-limit: 3 reset requests per hour per email (probably via Frappe `frappe.rate_limiter` if signature confirms in S26 probe; else custom)
- Portal UI: `/reset` page with email-entry form; `/reset/[token]` page with new-password form

**Dependencies:** PD-S26-AUTH-MS-GRAPH must land first.

#### PD-S26-AUTH-MS-GRAPH — Microsoft Graph wiring for outbound email

**Estimated:** 3-5 hours
**Scope:**
- Reuse Microsoft Graph credentials from VEMIO's existing config if available (verify in S26 A1 recon)
- New `vecrm/vecrm/utils/email.py` with `send_email(to: str, subject: str, body: str)` helper
- Token refresh logic
- Configuration via site config (NOT committed to repo)

**Optional Phase 2 (after reset works):** Use this same wiring for weekly meeting reports (B3 pillar from Session-0 vision).

#### PD-S26-AUTH-ADMIN-SET — `admin_set_credential` portal endpoint

**Estimated:** 3-4 hours
**Scope:**
- New whitelisted endpoint `vecrm.api.admin_set_credential(employee: str, password: str = None, pin: str = None)` — requires caller to have VECRM Admin role
- Today: equivalent functionality only via bench console (Ajay used this for Phase 5.A in S25)
- Portal UI: VECRM Admin gets a "Set credentials" button on Employee detail page

**Why deferred from S25:** S25 scope explicitly locked at email+password only; admin-set was console-only as a known limitation.

#### PD-S26-AUTH-CREDS-ROTATE — Rotate `encryption_key` and `vecrm_internal_secret`

**Estimated:** 2-3 hours
**Scope per OBS-S25-D:** rotate the Frappe encryption_key and the vecrm_internal_secret (used for any future internal-API signing). Coordinated procedure: capture old keys → generate new keys → re-encrypt any encrypted fields (Frappe handles this on `bench set-config` for encryption_key) → roll out → verify nothing broke → invalidate old keys.

**Note:** Now that `password_hash` is Data fieldtype (not Password), this rotation is *less* risky than it would have been mid-S25; passlib hashes don't depend on `encryption_key`.

### Highest priority — Portal continuation backlog

#### PD-S26-PORTAL-SUB-B-EXPENSE — Expense Voucher portal

**Estimated:** 10-16 hours
**Scope:** Portal-screens work on top of the existing Expense Voucher doctype family (already shipped in S23 PR #12). A1 recon banked from S24 dispatch D. Includes:
- `/expense-vouchers/new` (Compose + Review)
- `/expense-vouchers` (list)
- `/expense-vouchers/[name]` (detail)
- 3-4 new BFF routes mirroring Travel Voucher shape
- New backend endpoints: `create_expense_voucher_draft`, `submit_expense_voucher_draft`
- Attachment upload (MVP scope, per operator decision in S24)

**Why now:** Sub-A (Travel Voucher portal) works for all 3 roles post-S25. Sub-B is the symmetric next.

#### PD-S26-PORTAL-SUB-B2-APPROVER — Approver queue UI

**Estimated:** 6-10 hours
**Scope:** Backend `approve_travel_voucher` and `approve_expense_voucher` APIs already exist. Need:
- `/approver/queue` page — list submitted vouchers awaiting approval, filtered by approver_set
- Approve/Reject action UI on each row
- Detail view with action slots (placeholders exist from S24 PR #5)

**Dependencies:** Sub-B should land first so the queue can include EVs.

### Medium priority — quality-of-life

#### PD-S26-DEAD-AUTH-ME-ROUTE — Delete `app/api/auth/me/` (vecrm-portal)

**Estimated:** 10 min
**Scope:** Dead route; not touched in S25 Phase 3 because Option A scope locked the touch surface to 4 routes. Just delete the file + verify nothing imports it.

#### PD-S26-PORTAL-VECRMSESSION-TYPE — Expand `getFrappeUser` return type

**Estimated:** 1-2 hours
**Scope:** `getFrappeUser()` currently returns `string` (the employee_name). Expand to a `VecrmSession` interface with employee, name, vecrm_email, role, base_city, login_path. Update all call sites.

#### PD-S26-VOUCHER-DRAFT-CLEANUP — GC orphan voucher drafts

**Estimated:** 30 min
**Scope:** Scheduled task in `vecrm/hooks.py`: nightly job that deletes Travel/Expense Voucher drafts (`docstatus=0`) older than 7 days.

#### PD-S26-VOUCHER-DRAFT-RESUME — Resume-from-draft flow

**Estimated:** 2-3 hours
**Scope:** Currently, "Back to edit" on the new-voucher form creates a fresh draft each time. Implement proper resume: if a draft for the current user exists, load it instead of creating new.

### Low priority — schema cleanup (carried)

#### PD-S26-VOUCHER-CANCEL-AUDIT (CARRIED FROM S24)

**Estimated:** 30 min
**Scope:** `on_cancel(self)` hook on both VECRM Travel Voucher and VECRM Expense Voucher controllers, emitting to VECRM Voucher Audit Log. Cancellation is currently un-audited.

#### PD-S26-PHANTOM-SALES-VISIT-TABLE (CARRIED FROM S23)

**Estimated:** 15 min
**Scope:** `DROP TABLE tabVECRM Sales Visit` after verifying 0 rows. Doctype was retired in S8 but table cleanup never ran.

### Low priority — auth code cleanup

#### PD-S26-AUTH-FORMATTING-CONSISTENCY

**Estimated:** 30 min
**Scope:** Run `black` and `ruff` across the vecrm app. The S25 work introduced inconsistent quote styles and line-length patterns.

#### PD-S26-AUTH-VECRM-INIT-INVESTIGATION

**Estimated:** 1 hour (could be 5 min, could be 4 hours)
**Scope:** Investigate `vecrm/__init__.py` auto-import behavior surfaced as Phase 0.5 byproduct in S25 (OBS-S25-V). Possibly related to why runtime-added `@frappe.whitelist()` endpoints don't register.

#### PD-S26-AUTH-OBS-Z-AUDIT

**Estimated:** 30 min
**Scope:** Audit any remaining `get_decrypted_password` call sites in vecrm to confirm they're appropriate now that `password_hash` is Data fieldtype (per OBS-S25-Z).

#### PD-S26-DISPATCHER-DISCIPLINE-MECHANICAL-RULES

**Estimated:** 1-2 hours
**Scope:** Codify the OBS-S25 patterns as mechanical prevention rules. Mostly already locked via the 5 new S25 architectural lock files. Track any remaining gaps:
- Source artifacts via `present_files` (locked: VECRM-LOCK-FILE-DELIVERY-NOT-PASTE)
- `git log --oneline -5` before flagging a blocker (OBS-S25-AS — not yet locked; consider promoting if recurs in S26)
- No cross-turn source references (OBS-S25-AM/AN/AO — covered by FILE-DELIVERY lock)
- No mental-model code (general principle, recurs across sessions)
- Verified-symbol-only prescriptions (OBS-S25-AT — not yet locked)
- §risk → §verification-gate (locked: VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE)

---

## PART B — Strategic backlog (Session-0 pillars)

| Pillar | S22 status | S24 close | **S25 close** | Notes |
|---|---|---|---|---|
| B1 — Voucher portal | ❌ | ✅ Sub-A (Admin-only) | ✅ **Sub-A multi-user** | Sub-B (Expense) + Sub-B2 (Approver) pending |
| B2 — Approver portal | ❌ | ❌ | ❌ | PD-S26-PORTAL-SUB-B2-APPROVER |
| B3 — Weekly meeting report | ❌ | ❌ | ❌ | Could leverage PD-S26-AUTH-MS-GRAPH wiring |
| B4 — PWA validation | ⚠️ Manifest only | ⚠️ | ⚠️ | Blocked on TRAI DLT |
| B5 — Role differentiation | ⚠️ Backend-only | ⚠️ Blocked on auth | ✅ **UNBLOCKED** | Session→employee→role resolution works |
| B6 — Lead → Inquiry pipeline | ⚠️ Backend works | ✅ End-to-end | ✅ **Multi-user** | |
| B7 — Tally → ERPNext | ⚠️ Deferred | ⚠️ Deferred | ⚠️ Deferred | API-driven migration when started |
| B8 — TRAI DLT | ⚠️ Deferred | ⚠️ Deferred | ⚠️ Deferred | Multi-day operator-side paperwork |

---

## PART C — Infrastructure debt & operational items

### C1. No automated test suite

Promoting `§6` concurrency hard-gates to a permanent `tests/` directory is a register item carried since S22. **Still deferred.** Pattern to copy: VEMIO S56-S58 (Layer 1 CI: Dependabot, lint, Semgrep report-only).

### C2. No CI on PRs

Local pre-commit verification only (`npm run build`, `python -m py_compile`, AST checks). PRs merged on dispatcher-review of diffs, not on CI gates. Layer 1 CI would catch what slips today. **Carried.**

### C3. Test data in production database (CARRIED FROM S22)

`tabVECRM Voucher Counter` has rows from S22 §6 hard-gate tests. **Retained per audit policy** (no-delete rule from Session 0). Identifiable by submitter `+91-9999900001`. Acceptable to keep for regression testing.

S25 added more test data: VECRM Auth Audit Log has ~10 rows from Phase 4/5 smoke runs. Same policy — keep.

### C4. Container deploy pattern (carried documentation)

Pattern established across S20+:
- For Python file changes: `tar` → `scp` → `docker cp` → `docker exec ... tar -xzf` (NOT direct file replacement)
- For full image changes: `docker compose build --no-cache <service>` → `docker compose up -d <service>`
- VPS container at `/home/frappe/frappe-bench/apps/vecrm/` is NOT a git checkout (OBS-S25-AX); deployments are tar-based
- Post-deploy verification via `docker exec ... bench --site ... migrate` + smoke

### C5. Credential rotation procedure (NEW S25, partially scoped)

Per OBS-S25-D and PD-S26-AUTH-CREDS-ROTATE: site has `encryption_key` and `vecrm_internal_secret` that should be rotated. The procedure is documented at high level but not yet executed. S26 will execute and document the procedure.

### C6. Shared-VPS discipline (carried)

VECRM and VEMIO share Contabo Mumbai VPS at `217.216.58.117`. Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS: VECRM dispatcher NEVER touches VEMIO containers, files, or DB. Honored throughout S25.

---

## PART D — Architectural locks status

### Active locks (full list at S25 close)

**Numeric (pre-S23):**

- **VECRM-L8** — Allocator dual-surface sha verification. Banked sha: `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` (unchanged through S25)
- **VECRM-L10** — Strict gap-free allocator invariant
- **VECRM-L13** — Squash-merge + branch delete on PR merge (honored throughout S25)
- **VECRM-S22-A** — Counter allocator value-read invariant (read counter value INSIDE `SELECT ... FOR UPDATE`)

**Named (S23):**

- **VECRM-LOCK-AUTONAME-HYGIENE** — `autoname=''` is the only safe value (OBS-S23-B)
- **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** — name guards in `validate()` not `before_insert()` (OBS-S23-C)
- **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** — destructive VPS ops require dispatcher authorization

**Named (S24):**

- **VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE** — `app/[name]/...` routes decode at entry (OBS-S24-L/N/P)

**Named (S25, NEW):**

- **VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE** — Custom session-data writes via `frappe.session.data.*` + `frappe.local.session_obj.update(force=True)`. Never raw `frappe.cache.hset` on session slots. (OBS-S25-AL)
- **VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE** — Fields storing one-way hashes use Data fieldtype, not Password. (OBS-S25-AK)
- **VECRM-LOCK-PORTAL-USER-ROLES** — Shared portal user is Website User + Submitter+Approver only; role JSON has `desk_access:0` on portal roles. (OBS-S25-H/Y)
- **VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE** — §risk sections in dispatches MUST have a concrete verification check at the moment the risk becomes structurally concrete. (OBS-S25-AV)
- **VECRM-LOCK-FILE-DELIVERY-NOT-PASTE** — Source artifacts > ~30 lines via `present_files`, not inline chat code blocks. (OBS-S25-AP)

**Cross-cutting (PERMANENT):**

- **OBS-S71-A** — `git branch --show-current` before AND after every commit-bearing or merge-bearing bash invocation

### S25 OBS observations promoted to locks

5 of 47 OBS observations promoted to formal locks. The remaining 42 are filed in the close handover §11 but did not graduate this session.

### Hard constraints (carry forward)

- Schema migrations require atomic transaction + paired rollback file (VEMIO L22, observed in VECRM via S25 patches)
- File-scope `scp` only, no `scp -r` for file edits (VEMIO L24)
- Always run schema introspection (`bench --site ... console` + `frappe.get_meta(...)` or `\d <table>`) before any SQL probe

---

## PART E — Component-by-component build status (S25 close ground truth)

Per OBS-S22-B: this is the ACTUAL state, not what handover prose claims. Cross-check before relying.

### Layer 1 — Foundation doctypes

| Component | Status | Notes |
|---|---|---|
| VECRM Employee | ✅ | autoname=field:vecrm_phone. **S25: 4 credential fields added (password_hash Data, failed_password_attempts Int, locked_until Datetime, last_login_at Datetime). unique:1 on vecrm_email. 3 Active rows.** |
| VECRM Voucher Counter | ✅ | TV/EV/LEAD/INQ -26-27 all live. TV at 94. |
| VECRM Voucher Audit Log | ✅ | append-only, shared TV+EV |
| VECRM Inquiry Audit Log | ✅ | Q9 transport works |
| **VECRM Auth Audit Log (NEW S25)** | ✅ | append-only auth events |
| **VECRM Portal User (Frappe User, NEW S25)** | ✅ | `vecrm-portal@vinayenterprises.co.in` Website User + Submitter+Approver |
| Frappe Roles | ✅ | Submitter/Approver/Admin/Sales Head/HR; S25 fix: Submitter/Approver desk_access:0 |

### Layer 2 — Voucher pillar

| Component | Status | Notes |
|---|---|---|
| Travel Voucher | ✅ | **S25: multi-user via auth** |
| Visit Line (TV child) | ✅ | |
| Expense Voucher | ✅ | backend only; portal screens pending |
| Expense Line (EV child) | ✅ | |
| Rate Card | ✅ | Ahmedabad ₹2.5/km, Mumbai+Pune ₹3.5/km |
| approve_travel_voucher API | ✅ | |
| approve_expense_voucher API | ✅ | |
| Travel Voucher portal | ✅ | **S25: multi-user** |
| Expense Voucher portal | ❌ | **PD-S26-PORTAL-SUB-B-EXPENSE** |
| Approver portal | ❌ | **PD-S26-PORTAL-SUB-B2-APPROVER** |
| Voucher cancel audit | ❌ | **PD-S26-VOUCHER-CANCEL-AUDIT** (carried) |

### Layer 3 — Sales pipeline

| Component | Status | Notes |
|---|---|---|
| VECRM Lead | ✅ | **S25: Submitter+Approver perms added (Phase 5.5)** |
| VECRM Inquiry | ✅ | **S25: Admin+Submitter+Approver perms added (Phase 5.5; Admin row was missing pre-S25 — latent bug)** |
| convert_lead_to_inquiry API | ✅ | |
| Lead portal — list / detail / create | ✅ | |
| Inquiry portal — list / detail | ✅ | |
| VECRM Customer (skeleton) | ⚠️ | minimal; deferred to ERPNext migration |
| Quote / Order / Invoice | N/A | ERPNext domain |

### Layer 4 — Reporting & Workflow

| Component | Status | Notes |
|---|---|---|
| Weekly meeting report | ❌ | B3 backlog; could leverage MS Graph wiring from PD-S26-AUTH-MS-GRAPH |
| Sales activity dashboard | ❌ | depends on data accumulation |
| PWA (manifest only) | ⚠️ | blocked on TRAI DLT |
| Push notifications | ❌ | blocked on TRAI DLT |

### Authentication & Authorization (NEW LAYER, S25)

| Component | Status | Notes |
|---|---|---|
| Email+password login | ✅ | vecrm.api.login_with_password |
| Phone+PIN login | ❌ | **PD-S26-AUTH-PHONE-PIN** |
| Logout | ✅ | vecrm.api.vecrm_logout |
| Session→employee resolver | ✅ | vecrm.api.get_session_employee |
| Account lockout | ✅ | 5 attempts → 15 min window |
| Audit log emission | ✅ | success/failed/locked/logout |
| Password reset flow | ❌ | **PD-S26-AUTH-RESET** |
| Admin credential set | ❌ | **PD-S26-AUTH-ADMIN-SET** (console-only today) |
| MS Graph email delivery | ❌ | **PD-S26-AUTH-MS-GRAPH** |

### Cross-cutting infrastructure

| Component | Status | Notes |
|---|---|---|
| SSR cookie hydration (S23 shim) | ⚠️ | Admin-only; less critical post-S25 but not replaced |
| docs/portal-conventions.md | ✅ | S24 PR #14, 11 sections |
| docs/architectural-locks/ | ✅ | All locks have files; 5 new files added S25 |
| docs/session-handovers/ | ✅ | S22, S23, S24, S25 all present |

---

## PART F — Production data state

| Anchor | Value |
|---|---|
| Site | `crm.vinayenterprises.co.in` |
| VPS | 217.216.58.117 (Contabo Mumbai) |
| VPS RAM / CPU | 12GB / 6 cores |
| Frappe version | v16.18.2 |
| `require_type_annotated_api_methods` | ENABLED site-wide |
| Container | `vecrm-backend-1` |
| **`vecrm` main HEAD** | **`5e0df3b`** (post-PR #16) + S25-docs PR will increment |
| **`vecrm-portal` main HEAD** | **`8165f7a`** (post-PR #8, Vercel auto-deployed) |
| Allocator sha (L8) | `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` |
| Counter TV-26-27 | 94 |
| Counter LEAD-26-27 | 13 |
| Counter INQ-26-27 | 12 |
| Counter EV-26-27 | 12 |
| Production Frappe Users | 2 real (`ajay@`, `vecrm-portal@`), 3 demo seed |
| **Production VECRM Employees** | **3 Active** (Test Sales Rep +91-9999900001, Test HR Approver +91-9999900002, Ajay Salvi +91-9327547536) |
| Voucher audit log rows | ~13 (append-only) |
| **VECRM Auth Audit Log rows** | **~10** (Phase 4/5 smoke; append-only) |

---

## PART G — Known schema drift (S25 close)

### G1. Phantom `tabVECRM Sales Visit` table (CARRIED)

Doctype retired in S8, table not dropped. PD-S26-PHANTOM-SALES-VISIT-TABLE.

### G2. Counter test data (CARRIED)

S22 §6 hard-gate test rows. Retained per audit policy.

### G3. Lead doctype permissions (FIXED S24+S25)

S24 PR #15 added VECRM Admin row. **S25 PR #16 (Phase 5.5) added VECRM Submitter + VECRM Approver rows.**

### G4. Customer doctype skeleton (UNCHANGED)

Deferred pending Tally→ERPNext.

### G5. Voucher cancellation audit gap (CARRIED)

PD-S26-VOUCHER-CANCEL-AUDIT.

### G6. VECRM Inquiry doctype permissions (FIXED S25)

Pre-S25: only System Manager. Latent bug — Ajay had access only via Frappe Administrator superuser. **S25 PR #16 (Phase 5.5): added VECRM Admin + Submitter + Approver rows.** Latent bug → fixed.

### G7. VECRM Employee.password_hash __Auth orphans (NEW S25, CLEANED IN-SESSION)

Phase 4.7 migration dropped any stranded `__Auth` rows pre-fieldtype-change. No active drift.

---

## PART H — Out of VECRM scope (clarifications)

Carried from prior registers to prevent OBS-S22-B drift.

| Item | Owner | Why |
|---|---|---|
| Quote doctype | ERPNext | Beyond Inquiry is sales-quote territory |
| Order doctype | ERPNext | Sales-order management |
| Invoice / Credit Note | ERPNext | Tax / GST / e-invoicing complexity |
| Inventory | ERPNext / N/A | Vinay Enterprises is services-based |
| Payment reconciliation | ERPNext | Bank statements, GST returns |
| Tax templates / GST config | ERPNext + Indian Compliance app | Complex; deferred |
| TACACS+ / RADIUS / network device auth | VEMIO | Wrong product entirely |
| Network monitoring / alerts / SLAs | VEMIO | Wrong product entirely |
| GLPI ticketing | VEMIO (decommissioned S64) | Not VECRM |

---

**End of VECRM-PENDENCY-REGISTER.md**

This register is regenerated comprehensively at every session close per VECRM-L2 (decisions written, not remembered). Surgical edits between session closes are acceptable; the register is fully reviewed and regenerated at session boundaries.
