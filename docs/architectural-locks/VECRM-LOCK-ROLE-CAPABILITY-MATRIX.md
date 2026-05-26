# VECRM-LOCK-ROLE-CAPABILITY-MATRIX

**Earned:** S32 (PD-S29-ROLE-MATRIX-LOCK; required prerequisite for Sales Rep hiring)
**Status:** ACTIVE
**Severity:** Critical (privilege boundary; user-onboarding gate)
**Companion locks:** `VECRM-LOCK-PORTAL-USER-ROLES` (S25), `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE` (S25)

---

## Statement

The VECRM application recognizes exactly **6 employee roles**. Each role has a fixed, auditable set of capabilities across every functional surface (Lead, Inquiry, Voucher, Account, Admin). This document is the canonical capability matrix.

Every PR that introduces, removes, or alters a role capability MUST update this lock doc in the same commit as the code change. PRs that touch role-gated behavior without referencing this lock will be rejected on review.

This lock consolidates and supersedes all prior informal role discussions. It is the source of truth for: hiring (who needs what role), endpoint authorization (who can call what), and security review (what role can do what damage if compromised).

---

## §1 — The 6 VECRM Employee roles

The role enum is canonical at `vecrm/vecrm/utils/roles.py` (backend) and mirrored at `vecrm-portal/lib/roles.ts` (portal). Backend is authoritative; the portal mirror must not drift.

| # | Role | Intent | Voucher submission | Admin bypass |
|---|---|---|---|---|
| 1 | **Admin** | Founder / CTO / future user-admin staff | No (system role, not field-staff) | ✅ Yes |
| 2 | **Sales Head** | Manages Sales Reps; approves their vouchers | No | ❌ No (own data only — see §3.3) |
| 3 | **HR** | People ops; approves any voucher | No | ❌ No |
| 4 | **Sales Rep** | Field sales; creates Leads and Inquiries | ✅ Travel + Expense | ❌ No |
| 5 | **Field Engineer** | Service engineer; creates field reports & vouchers | ✅ Travel + Expense | ❌ No |
| 6 | **Head of Engineers** | Manages Field Engineers; approves their travel vouchers | No | ❌ No |

**Constraints:**

- An employee has **exactly one** role. There is no multi-role assignment.
- The role is stored on `VECRM Employee.role` and surfaced into the session as `frappe.session.data.vecrm_employee_role` (backend) / `session.role` (portal).
- New roles MUST NOT be added without updating both `roles.py` AND `roles.ts` AND this lock doc in a single PR.

**Cross-references:**

- Role enum definition (backend): `vecrm/vecrm/utils/roles.py`
- Role enum mirror (portal): `vecrm-portal/lib/roles.ts:13-19`
- Type guard (portal): `vecrm-portal/lib/roles.ts:isVecrmRole`
- Admin bypass helper (portal): `vecrm-portal/lib/roles.ts:isAdminRole`
- Role resolution from session: `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE`

---

## §2 — Role resolution mechanism

**The Frappe-side authentication user is shared.** All portal-authenticated requests run as the shared `vecrm-portal@vinayenterprises.co.in` user. The per-employee identity is in the session data, not in Frappe's auth layer.

The resolution chain on every authenticated portal request:

1. Browser sends `sid` cookie.
2. Frappe loads the session for that sid, restoring `frappe.session.data` (the inner payload).
3. `frappe.session.data.vecrm_employee_phone` identifies the VECRM Employee.
4. `frappe.session.data.vecrm_employee_role` is the role for this request.
5. Endpoints that need role gating MUST read step 4 — NEVER `frappe.get_roles()`, which returns the shared user's Frappe roles (always `VECRM Submitter + VECRM Approver`).

**Critical reminder:** `frappe.get_roles()` for the shared portal user always returns the same set regardless of which employee is logged in. Role-differentiated behavior MUST use `frappe.session.data.vecrm_employee_role`. See `VECRM-LOCK-PORTAL-USER-ROLES` for the full rationale.

**Critical reminder:** Custom session-data writes MUST persist via `frappe.local.session_obj.update(force=True)` after mutating `frappe.session.data.*`. NEVER write directly to the session cache slot. See `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE` for the mechanism.

---

## §3 — Architectural floors (non-negotiables)

These five floors are inviolate. Any PR that proposes to change them requires a security review AND an update to this lock doc AND the operator's explicit approval.

### §3.1 — Single admin role

`Admin` is the **only** admin-bypass role. There is no "Super Admin", no "Owner", no implicit admin promotion via role combination. If a 7th admin-tier role is ever proposed, it MUST be added as a new explicit enum value AND `isAdminRole()` MUST be updated AND this lock doc MUST be revised.

```ts
// vecrm-portal/lib/roles.ts
export function isAdminRole(role: VecrmRole | string): boolean {
  return role === "Admin";   // ← exactly this. Not array membership. Not regex.
}
```

### §3.2 — No hierarchical visibility

Sales Head does **NOT** see their Sales Reps' Leads. Head of Engineers does **NOT** see their Field Engineers' visits. Every non-admin role is scoped strictly to `creating_employee = self.phone`.

The voucher approval hierarchy (§5) is a SEPARATE concern from data visibility. A Sales Head can APPROVE a Sales Rep's voucher but cannot READ the Sales Rep's Leads. This separation is intentional.

If hierarchical visibility is ever required (e.g., for management dashboards), it MUST be implemented as an explicit additive layer with its own audit trail, not by relaxing the scoping floor.

### §3.3 — Scoping returns 404 on deny, never 403

When a non-admin tries to read a row they don't own, the response is **HTTP 404 Not Found**, not 403 Forbidden. This is deliberate: 403 leaks the existence of rows the requester shouldn't know about.

```ts
// vecrm-portal/lib/scoping.ts:canReadLead
// On false return, the BFF returns HTTP 404 (not 403) per
// PD-S28-LEAD-SCOPING-CUTOVER §2.3 — don't leak existence.
```

**Note:** HTTP 403 in the VECRM stack is reserved for `SessionStopped` (stale sid). See `PD-S31-PORTAL-SESSION-EXPIRY-UX`. The portal's `useApiFetch` interprets 403 as "session expired, redirect to login," NOT as "access denied to this row."

### §3.4 — Defense-in-depth gap acknowledged

Currently, scoping is enforced at the **portal BFF layer** (`canReadLead`, `getScopedLeadFilter`). The Frappe whitelist endpoints themselves (`close_lead`, `close_inquiry`, `convert_lead_to_inquiry`, etc.) do **NOT** re-verify scoping at the backend.

This means: a user with a valid sid can craft a direct curl call to `close_lead("VE/LEAD/XXX")` where XXX is a Lead they don't own, and the backend will close it.

**Known pendency:** `PD-S32+-BACKEND-SCOPING-DEFENSE-IN-DEPTH` (P2) — port the BFF scoping logic into the whitelist endpoints themselves, so the backend enforces independently of the portal. Until this lands, the portal BFF is the sole scoping enforcement layer. Treat BFF route correctness as security-critical.

### §3.5 — One employee, one role

There is no concept of an employee having multiple roles. The `VECRM Employee.role` field is a single-value enum. Multi-role hierarchies (e.g., "Sales Rep who is also acting Sales Head") are NOT supported.

If a person transitions roles, their `VECRM Employee.role` is **updated in place** (with audit logging). No second row, no "additional roles" child table.

---

## §4 — The capability matrix

Legend:
- ✅ — allowed
- ❌ — denied
- 🔒 — admin-only
- 📦 — scoped to own data (creator-match required)
- ⏳ — endpoint exists, currently no enforcement (see gaps in §6)

### §4.1 — Lead capabilities

| Capability | Endpoint / surface | Admin | Sales Head | HR | Sales Rep | Field Engineer | Head of Engineers |
|---|---|---|---|---|---|---|---|
| Create | `POST /api/leads` → `vecrm.api.create_lead` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| List | `GET /api/leads` | ✅ all | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |
| Read (single) | `GET /api/leads/[name]` | ✅ any | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |
| Update fields | `POST /api/leads/[name]` (via Frappe REST) | ✅ any | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |
| Close (Won/Lost) | `POST /api/leads/[name]/close` → `vecrm.api.close_lead` | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| Convert to Inquiry | `POST /api/leads/[name]/convert` → `vecrm.api.convert_lead_to_inquiry` | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| Upload attachment | `POST /api/leads/[name]/attachments?slot=N` | ✅ | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |
| Delete attachment | `DELETE /api/leads/[name]/attachments?slot=N` | ✅ | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |

**Note on Create:** Every role can technically create a Lead via the portal. In practice, only Sales Rep, Field Engineer, and Admin use this surface. Non-sales-facing roles (HR, Sales Head, Head of Engineers) creating Leads is unusual but not forbidden.

**Note on ⏳ Close + Convert:** The backend endpoints do not currently re-check scoping. The portal BFF route MUST call `canReadLead()` before proxying to these endpoints. If the BFF check is missing, any role with a valid sid can close/convert any Lead. This is the §3.4 defense-in-depth gap manifesting concretely.

### §4.2 — Inquiry capabilities

| Capability | Endpoint / surface | Admin | Sales Head | HR | Sales Rep | Field Engineer | Head of Engineers |
|---|---|---|---|---|---|---|---|
| Create | Via Lead conversion only (`convert_lead_to_inquiry`) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| List | `GET /api/inquiries` | ✅ all | ⚠️ all | ⚠️ all | ⚠️ all | ⚠️ all | ⚠️ all |
| Read (single) | `GET /api/inquiries/[name]` | ✅ any | ⚠️ any | ⚠️ any | ⚠️ any | ⚠️ any | ⚠️ any |
| Close | `POST /api/inquiries/[name]/close` → `vecrm.api.close_inquiry` | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**⚠️ Critical gap:** Inquiry endpoints do **NOT** have a scoping filter equivalent to `getScopedLeadFilter()`. All authenticated sessions currently see ALL Inquiries. This is tracked as `OBS-S31-Y` and corresponds to pendency `PD-S32+-INQUIRY-SCOPING` (P1 once user-onboarding begins). Until this lands, treat Inquiry visibility as system-wide for all non-admin roles.

### §4.3 — Travel Voucher capabilities

| Capability | Endpoint / surface | Admin | Sales Head | HR | Sales Rep | Field Engineer | Head of Engineers |
|---|---|---|---|---|---|---|---|
| Submit (create draft) | `vecrm.api.create_travel_voucher_draft` | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| Submit (finalize) | `vecrm.api.submit_travel_voucher_draft` | ❌ | ❌ | ❌ | ✅ (own draft) | ✅ (own draft) | ❌ |
| Read own drafts/submitted | `GET /api/travel-vouchers` | ✅ all | 📦 own | 📦 own | 📦 own | 📦 own | 📦 own |
| **Approve Sales Rep's voucher** | `vecrm.api.approve_travel_voucher` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Approve Field Engineer's voucher** | `vecrm.api.approve_travel_voucher` | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |

**Submission eligibility** is hard-gated by `APPROVER_SETS` in `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py:27`. Only the 2 roles present as keys can submit:

```python
APPROVER_SETS: dict[str, list[str]] = {
    "Sales Rep": ["Sales Head", "HR", "Admin"],
    "Field Engineer": ["Head of Engineers", "HR", "Admin"],
}
```

**Approval matrix** is derived directly from `APPROVER_SETS` and snapshotted onto the voucher row at validate-time as `approver_role_set` (a JSON list of role strings). Approval check: the approver's `VECRM Employee.role` must be in the voucher's `approver_role_set`. First-to-approve wins.

### §4.4 — Expense Voucher capabilities

| Capability | Endpoint / surface | Admin | Sales Head | HR | Sales Rep | Field Engineer | Head of Engineers |
|---|---|---|---|---|---|---|---|
| Submit | `vecrm/vecrm/doctype/vecrm_expense_voucher` controller | ⏳ | ⏳ | ⏳ | ✅ | ✅ | ⏳ |
| Approve | `approve_expense_voucher` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

**Expense voucher approver-set is uniform regardless of submitter role:** `["Sales Head", "HR", "Admin"]`. This is hardcoded at `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:128`.

**Asymmetry with Travel Voucher:** Head of Engineers can approve a Field Engineer's *travel* voucher but NOT their *expense* voucher. This is intentional per S23 spec (expense approval is centralized in finance-adjacent roles: Sales Head / HR / Admin). If this becomes operationally inconvenient, the policy may be updated — but the change requires an explicit lock-doc revision.

**Naming inconsistency (banked observation):** Travel voucher uses `approver_role_set` (column name); Expense voucher uses `approver_set`. Schema hygiene; not load-bearing, not worth migration churn. See `OBS-S32-RM-NAMING` below.

### §4.5 — Account / self-service capabilities

| Capability | Endpoint / surface | All 6 roles |
|---|---|---|
| Read own profile | `GET /api/me` → `vecrm.api.get_session_employee` | ✅ |
| Change own password | `POST /api/account/change-password` → `vecrm.api.change_password` | ✅ |
| Change own PIN | `POST /api/account/change-pin` → `vecrm.api.change_pin` | ✅ |
| Request password reset | `POST /api/auth/forgot-password` → `vecrm.api.request_password_reset` | ✅ (public, allow_guest) |
| Request PIN reset | `POST /api/auth/forgot-pin` → `vecrm.api.request_pin_reset` | ✅ (public, allow_guest) |
| Login (password) | `POST /api/auth/login` → `vecrm.api.login_with_password` | ✅ (public, allow_guest) |
| Login (PIN) | `POST /api/auth/login-pin` → `vecrm.api.login_with_pin` | ✅ (public, allow_guest) |
| Logout | `POST /api/auth/logout` → `vecrm.api.vecrm_logout` | ✅ |

All 6 roles can do all of the above. These are universal session-management capabilities.

### §4.6 — Admin / management capabilities

| Capability | Endpoint / surface | Admin | All others |
|---|---|---|---|
| Read all Leads (cross-employee) | List/detail without scoping filter | ✅ (no filter applied) | ❌ |
| Read all Inquiries | Same | ✅ | ⚠️ See §4.2 gap |
| User management page | `PD-S29-ADMIN-USER-MGMT-PAGE` (not yet built) | ✅ (pending) | ❌ |
| Role assignment | Currently Desk-only (Frappe Desk) | ✅ (Desk) | ❌ |
| Rate Card management | `GET /api/rate-cards` (read-only); Desk for edits | All ✅ read | 🔒 Desk-only edits |
| Audit log read | Currently Desk-only | ✅ (Desk) | ❌ |

**The Admin role's bypass is "no filter applied", not "permission to bypass."** Admin users see all data because `isAdminRole()` causes `getScopedLeadFilter()` to return null. There is no separate admin-permission check.

This means: **the integrity of the entire access-control model rests on `isAdminRole()` being correct.** Any change to that function is a security-critical PR.

---

## §5 — Voucher approval policy (formal)

This section formalizes the policy implied by `APPROVER_SETS` (travel) and the hardcoded `approver_roles` list (expense).

### §5.1 — Travel Voucher approval

```
Submitter           Eligible approvers (any one approves)
─────────────────   ─────────────────────────────────────
Sales Rep           Sales Head, HR, Admin
Field Engineer      Head of Engineers, HR, Admin
```

Implementation: `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py:27`. The mapping is snapshotted onto the voucher at validate-time so subsequent role changes (e.g., a Sales Rep being promoted to Sales Head) do not retroactively change the eligible approver set.

### §5.2 — Expense Voucher approval

```
Submitter           Eligible approvers (any one approves)
─────────────────   ─────────────────────────────────────
Sales Rep           Sales Head, HR, Admin
Field Engineer      Sales Head, HR, Admin
(others)            (no submission allowed)
```

Implementation: `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:128`. Hardcoded; does not vary by submitter.

### §5.3 — First-to-approve wins

Both travel and expense vouchers follow a **first-to-approve** model. If a Sales Rep submits a travel voucher, ANY ONE of Sales Head / HR / Admin can approve it. Once approved, subsequent approval attempts are rejected (`docstatus` becomes 1).

There is NO multi-stage approval, NO co-approval, NO threshold-based escalation. If amount-threshold approval is ever needed (e.g., "vouchers over ₹50,000 require Admin approval"), it MUST be added as a new policy layer with an explicit lock-doc revision.

### §5.4 — Audit trail

Every voucher submission and approval writes to `VECRM Voucher Audit Log`. The actor identity recorded is `frappe.session.data.vecrm_email` (NOT `frappe.session.user`, which would be the shared portal user). See `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE` for the session-data write mechanism and `OBS-S31` (LEAD-OWNER-ATTRIBUTION fix) for the actor-identity correction history.

---

## §6 — Known gaps and pendencies

These are gaps in the current implementation that this lock acknowledges but does not currently mandate fixing. They are tracked as pendencies and will be resolved per the pendency register sequencing.

| # | Gap | Severity | Tracked as |
|---|---|---|---|
| G-1 | Inquiry endpoints have no scoping filter — all roles see all Inquiries | P1 (blocks Sales Rep go-live) | `PD-S32+-INQUIRY-SCOPING`, OBS-S31-Y |
| G-2 | Backend whitelist endpoints don't re-verify scoping; relies on BFF | P2 (defense-in-depth) | `PD-S32+-BACKEND-SCOPING-DEFENSE-IN-DEPTH` |
| G-3 | Admin user-management page not yet built | P1 (blocks Sales Rep onboarding) | `PD-S29-ADMIN-USER-MGMT-PAGE` |
| G-4 | Role assignment is Desk-only (no portal UI) | P2 | Subsumed by G-3 |
| G-5 | No hierarchical visibility (Sales Head can't see reports' Leads) | P3 (intentional today; may revisit) | Not blocking; design decision |
| G-6 | Travel uses `approver_role_set` column; Expense uses `approver_set` (naming inconsistency) | P4 (hygiene) | `OBS-S32-RM-NAMING` |
| G-7 | Audit log read access is Desk-only (no portal UI) | P3 | Future pendency |
| G-8 | No amount-threshold approval logic on either voucher type | P3 (future requirement) | Future pendency |

**Sales Rep go-live blocking gaps:** G-1, G-3. These MUST close before the first Sales Rep is hired. G-2 SHOULD close in the same window but is acceptable as a fast-follow.

---

## §7 — Validation procedure

To verify the role matrix is correctly implemented at any session, run these probes via `bench console` on the production VPS:

### §7.1 — Verify role enum (backend)

```python
import frappe
from vecrm.vecrm.utils.roles import ALL_ROLES, is_employee_admin

print(f"ALL_ROLES: {ALL_ROLES}")
# Expected: ['Admin', 'Sales Head', 'HR', 'Sales Rep', 'Field Engineer', 'Head of Engineers']

for r in ALL_ROLES:
    print(f"{r}: admin_bypass={is_employee_admin(r)}")
# Expected: only Admin shows True
```

### §7.2 — Verify role enum mirror (portal)

```bash
cd ~/Documents/GitHub/vecrm-portal
grep -A 10 "export type VecrmRole" lib/roles.ts
# Expected: same 6 strings as backend ALL_ROLES
grep -A 3 "export function isAdminRole" lib/roles.ts
# Expected: `return role === "Admin";`
```

### §7.3 — Verify the shared portal user invariant

Per `VECRM-LOCK-PORTAL-USER-ROLES` §Validation procedure:

```python
import frappe
user = "vecrm-portal@vinayenterprises.co.in"
print("user_type:", frappe.db.get_value("User", user, "user_type"))
# Expected: Website User
print("roles:", sorted(frappe.get_roles(user)))
# Expected: ['All', 'Guest', 'VECRM Approver', 'VECRM Submitter']
```

### §7.4 — Verify voucher approver mappings

```python
from vecrm.vecrm.doctype.vecrm_travel_voucher.vecrm_travel_voucher import APPROVER_SETS
print(APPROVER_SETS)
# Expected:
# {"Sales Rep": ["Sales Head", "HR", "Admin"],
#  "Field Engineer": ["Head of Engineers", "HR", "Admin"]}
```

Verify expense voucher approver list by inspection at `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:128`:

```python
approver_roles = ["Sales Head", "HR", "Admin"]
```

### §7.5 — Verify scoping helpers (portal)

```bash
cd ~/Documents/GitHub/vecrm-portal
grep -A 5 "export async function getScopedLeadFilter" lib/scoping.ts
grep -A 5 "export async function canReadLead" lib/scoping.ts
# Expected: both check isAdminRole(session.role); admin returns null/true respectively
```

### §7.6 — Verify §3.3 (404-not-403 on scoping deny)

Manual: as a non-admin user, attempt to fetch a Lead created by a different employee. The portal should return HTTP 404, NOT 403. If 403 is returned, that's the SessionStopped handler — verify the test setup.

---

## §8 — Change protocol

Any PR that changes role behavior MUST:

1. **Update this lock doc in the same commit.** No exceptions. The PR description must explicitly link the lock-doc change.
2. **Update both `roles.py` and `roles.ts`** if the role enum itself changes. Drift between backend and portal is a Critical-severity bug.
3. **Update `APPROVER_SETS`** (and this doc's §5) if approval policy changes.
4. **Cross-reference any affected gaps in §6.** Closing a gap means moving the entry from §6 to the matrix proper with the new enforcement detail.
5. **Re-run §7 validation procedure** before merge. Paste the validation output in the PR description.

### §8.1 — Adding a new role

Add a 7th role only if no existing role covers the use case. The process:

1. Draft a PR adding the role string to `roles.py` AND `roles.ts` AND this doc.
2. Update `isAdminRole()` if the new role is an admin variant (rare — should require explicit operator approval).
3. Add a row to every matrix table in §4 for the new role.
4. Update `APPROVER_SETS` if the new role can submit vouchers.
5. Update §1 with the role's intent.
6. Re-run §7 validation; include output in PR.

### §8.2 — Removing or merging a role

Removal requires:

1. Migration patch to reassign all `VECRM Employee.role = '<removed_role>'` rows to a target role (operator-confirmed).
2. Removal from `roles.py`, `roles.ts`, this doc, `APPROVER_SETS`.
3. Audit-log entry for each migrated employee.
4. PR description must justify removal AND document the migration plan.

### §8.3 — Changing approver policy

Changing `APPROVER_SETS` or expense `approver_roles` requires:

1. Operator approval (this is policy, not implementation).
2. Update §5 of this doc with old policy → new policy diff.
3. Verify no in-flight vouchers reference the changed sets (they're snapshotted at validate-time, so historical vouchers are safe — but draft vouchers are not).

---

## §9 — Application sites (file:line cross-references)

This section is the canonical map from "role behavior" to "where it's enforced in code." Update whenever code moves.

### §9.1 — Backend (vecrm/)

| Concern | File:line |
|---|---|
| Role enum (canonical) | `vecrm/vecrm/utils/roles.py` |
| Admin-bypass check | `vecrm/vecrm/utils/roles.py::is_employee_admin` |
| Session role write | `vecrm/api.py::_issue_session` |
| Session role read | Per-endpoint: `frappe.session.data.get("vecrm_employee_role")` |
| Lead create | `vecrm/api.py:380 @frappe.whitelist() def create_lead` |
| Lead close | `vecrm/api.py:437 @frappe.whitelist() def close_lead` |
| Lead convert | `vecrm/api.py: convert_lead_to_inquiry` |
| Inquiry close | `vecrm/api.py:491 @frappe.whitelist() def close_inquiry` |
| Travel voucher approver-set | `vecrm/vecrm/doctype/vecrm_travel_voucher/vecrm_travel_voucher.py:27 APPROVER_SETS` |
| Travel voucher approve | `vecrm/api.py: approve_travel_voucher` |
| Expense voucher approver-set | `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:128` |
| Expense voucher approve | `vecrm/vecrm/doctype/vecrm_expense_voucher/vecrm_expense_voucher.py:177 approve_expense_voucher` |
| Session-data persistence pattern | `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE` |
| Shared portal user invariant | `VECRM-LOCK-PORTAL-USER-ROLES` |

### §9.2 — Portal (vecrm-portal/)

| Concern | File:line |
|---|---|
| Role enum (mirror) | `lib/roles.ts:13-19` |
| Admin-bypass check | `lib/roles.ts:isAdminRole` |
| Session resolution (rich) | `lib/auth-ssr.ts:getVecrmSession` |
| Session resolution (legacy/name-only) | `lib/auth-ssr.ts:getFrappeUser` |
| Lead list scoping | `lib/scoping.ts:getScopedLeadFilter` |
| Single-Lead authz predicate | `lib/scoping.ts:canReadLead` |
| Lead list BFF | `app/api/leads/route.ts` |
| Lead detail BFF | `app/api/leads/[name]/route.ts` |
| Lead close BFF | `app/api/leads/[name]/close/route.ts` |
| Lead convert BFF | `app/api/leads/[name]/convert/route.ts` |
| Lead attachment BFF | `app/api/leads/[name]/attachments/route.ts` |
| Inquiry list BFF (NO scoping — gap G-1) | `app/api/inquiries/route.ts` |
| Inquiry detail BFF (NO scoping — gap G-1) | `app/api/inquiries/[name]/route.ts` |
| Inquiry close BFF (NO scoping — gap G-1) | `app/api/inquiries/[name]/close/route.ts` |
| Session-expiry handling | `lib/useApiFetch.ts`, `app/LoginForm.tsx` (see `PD-S31-PORTAL-SESSION-EXPIRY-UX`) |

---

## §10 — Banking observations from S32 authoring

These observations surfaced while authoring this lock and are captured here for the S32 close.

**OBS-S32-RM-NAMING** — Schema column-naming inconsistency: Travel Voucher uses `approver_role_set`, Expense Voucher uses `approver_set`. Acceptable as-is (no functional impact; both store a JSON list of role strings). If a future schema-cleanup PR rolls multiple naming fixes, rename to a consistent `approver_role_set` across both doctypes for consistency. Tracked as gap G-6.

**OBS-S32-RM-INQUIRY-SCOPING** — Inquiry endpoints (`/api/inquiries`, `/api/inquiries/[name]`, close, etc.) lack the `getScopedLeadFilter` / `canReadLead` equivalents that Lead endpoints have. All authenticated sessions see all Inquiries. This is gap G-1. Was previously banked as OBS-S31-Y; reconfirmed here. Must close before Sales Rep go-live.

**OBS-S32-RM-BACKEND-DEFENSE** — Backend whitelist endpoints (`close_lead`, `close_inquiry`, `convert_lead_to_inquiry`, voucher submit/approve) trust the BFF for scoping. A user crafting direct curl calls with a valid sid can bypass scoping if they know a target row name. This is gap G-2. Defense-in-depth pendency.

**OBS-S32-RM-NO-HIERARCHY** — Sales Head cannot see Sales Reps' Leads; Head of Engineers cannot see Field Engineers' visits. This was a deliberate design choice but should be re-evaluated once Sales Rep onboarding is operational and management asks for visibility dashboards. Tracked as gap G-5; not blocking.

---

## §11 — Related locks and observations

- `VECRM-LOCK-PORTAL-USER-ROLES` — the shared Frappe portal user invariant (foundational; this lock builds on it)
- `VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE` — how `vecrm_employee_role` is written into the session; foundational
- `VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE` — any risky change to role behavior is verification-gated; this lock IS that verification's substrate
- `VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY` — orthogonal but related auth-trust boundary; uses the same "hardcoded enumeration" discipline as this lock applies to roles
- `PD-S28-LEAD-SCOPING-CUTOVER` — the recon that introduced the scoping helpers cited throughout
- `PD-S31-PORTAL-SESSION-EXPIRY-UX` — the 403/SessionStopped handler that complements role-based 404s
- `OBS-S31-Y` — the originally-banked Inquiry-scoping gap (now formalized here as G-1)

---

## §12 — When this lock can be relaxed

Never relaxed. Can only be **revised** via the change protocol in §8. A "relaxation" of a role's capability is functionally a change to the matrix and must follow §8.

The closest case to "relaxation" is closing a gap from §6 by extending capabilities (e.g., adding Inquiry scoping that previously didn't exist). That's an additive change to the floor, not a relaxation, and follows the standard change protocol.

---

## §13 — Application to non-VECRM contexts

The pattern generalizes: any product with a fixed role enum and per-role capabilities should maintain a single canonical matrix document with:
- Explicit roles enumerated
- Capability axes enumerated
- Architectural floors stated
- Gaps explicitly tracked
- Change protocol mandated
- File:line cross-references to enforcement

Vemio's dashboard does not currently maintain a role matrix (single-role product). If Vemio grows multi-role behavior, it should adopt this lock format.

---

**End of VECRM-LOCK-ROLE-CAPABILITY-MATRIX.**
