# VECRM Portal Conventions

Established by S24 PD-S24-PORTAL-VOUCHER-SCREENS sub-A. Reference for
all downstream portal sub-projects (Sub-B Expense Voucher, B2 Approver
Portal, future portal create flows). Auth-related conventions are
deferred to PD-S25-VECRM-AUTH; this doc is updated when that ships.

## 1. Resource-route shape

Every VECRM portal resource follows this BFF route convention:

- `POST /api/<resource>`                 — create draft
- `POST /api/<resource>/[name]/<action>` — advance state (submit, approve, cancel)
- `GET  /api/<resource>/[name]`          — read one
- `GET  /api/<resource>`                 — list with filters

Concrete sample — the Travel Voucher resource shipped in Sub-A:

```
POST /api/travel-vouchers
  body: { submitter, business_date, visit_lines: [ {visit_date,
          customer_name, start_odometer, end_odometer, notes?}, ... ] }
  -> { ok: true, data: { name, total_km, total_amount, fy_label,
                          visit_lines: [...computed...], ... } }

GET  /api/travel-vouchers?docstatus=0&limit=100
  -> { ok: true, data: [ { name, submitter, business_date,
                            total_amount, docstatus, creation }, ... ] }

GET  /api/travel-vouchers/<name>
  -> { ok: true, data: { ...full voucher doc incl. visit_lines } }

POST /api/travel-vouchers/<name>/submit
  -> { ok: true, data: { name, docstatus: 1, total_amount, submitted_at } }
```

The BFF route forwards to a whitelisted backend endpoint
(`vecrm.api.*`) for create/submit, and to Frappe's generic
`/api/resource/<DocType>` for list/read.

## 2. BFF route conventions

- `export const dynamic = "force-dynamic"` on every BFF route
- Cookie forwarded via `(await cookies()).toString()`
- `frappeFetch` server-side only — never imported in client components
- Response shape: `{ok: boolean, data?: T, error?: string, status?: number}`
- Errors: 4xx pass through with the backend error message; 5xx for unexpected
- The client never calls Frappe directly — it calls `fetch("/api/<...>")`,
  the BFF route calls `frappeFetch`. sid-cookie auth only; no CSRF token
  is required for these cookie-authenticated calls (verified by the
  pre-existing lead-convert route).

## 3. Create-flow UX convention

Compose → Review → Submitting (modal) → Detail. Established in S24.

- Server-side totals: draft insert runs `validate()` which computes
  totals. The portal reads the computed values back for the Review
  screen.
- The portal does NOT mirror rate-card logic client-side.
- Direct submit (no save-draft button). Abandoned drafts persist in the
  DB, garbage-collected by a future scheduled task
  (PD-S25-VOUCHER-DRAFT-CLEANUP).
- The Review screen IS the gate. The Submitting modal is a progress
  indicator only.

## 4. Action-panel slot convention (detail views)

Each detail page renders three DOM-level slot markers as placeholders:

```tsx
<div data-slot="approver" className="action-slot">{/* Approver actions */}</div>
<div data-slot="admin"    className="action-slot">{/* Admin actions */}</div>
<div data-slot="submitter" className="action-slot">{/* Submitter actions */}</div>
```

- Slot A (approver): filled by B2 Approver Portal
- Slot B (admin): filled when PD-S24-VOUCHER-CANCEL-AUDIT closes
- Slot C (submitter): filled when S25 VECRM Auth establishes session
  identity for non-Admin users

Sub-A renders all three as `display: none` placeholders (`.action-slot`).
Downstream subprojects ADD content to the appropriate div; they do not
replace the slot structure.

## 5. Audit payload extension convention

The VECRM Voucher Audit Log controller auto-merges, on every row:

- `voucher_name`: the affected voucher
- `voucher_doctype`: e.g. "VECRM Travel Voucher"
- `actor_user`: `frappe.session.user` (who pressed the button)

The emitting caller's payload adds domain fields. For voucher submit,
the row already carries snapshot fields: `actor_employee`, `actor_role`,
`from_state`, `to_state`, plus event-specific amounts.

**Admin-override detection.** Because the audit row stores
`actor_employee` (the VECRM Employee the action is attributed to)
AND `actor_user` (the Frappe User who actually performed it) as
distinct snapshot fields, override detection is a direct comparison on
the row itself — no need to compute `actor_user` vs
`linked_user_of(submitter)` at consumer time. When `actor_user` does
not correspond to `actor_employee`'s own login identity, the action
was delegated (an Admin filed on behalf of the employee). In Sub-A's
Admin-only interim, `actor_user` is always the Admin (Ajay) and
`actor_employee` varies per voucher — so every Sub-A row reads as a
delegated action, which is correct for the interim. S25 VECRM Auth
formalizes the employee↔user correspondence the detection keys on.

## 6. Identity resolution convention (DEFERRED to S25)

S25 PD-S25-VECRM-AUTH establishes:

- Two-path login: phone + 6-digit PIN, or email + password
- A single VECRM Employee identity per user
- A session→employee resolution helper (replaces what v2 of S24's
  dispatch proposed as `vecrm.vecrm.utils.identity.resolve_submitter_employee`)
- Portal `/api/me` becomes employee-aware (returns the authenticated
  VECRM Employee with role, base_city, etc.)

Sub-A's `/api/me` returns only the Frappe User email — a minimal
placeholder that S25 augments. Sub-A's backend endpoints take
`submitter` as an explicit required parameter; that signature is stable
across the S25 transition — only the BFF route's *source* for the
parameter changes (Admin picker → resolved session identity).

## 7. Type annotation convention

Per Frappe v16 `require_type_annotated_api_methods` (site config):

- All `@frappe.whitelist()` methods need full type annotations on
  parameters and return.
- `from typing import Optional` allowed at module top — but only import
  what the code actually uses (an unused typing import is a defect; see
  OBS-S24-G).
- `dict` is acceptable as a return type; specific TypedDicts preferred
  when the shape is stable.

## 8. Backend API field naming — translation layer convention

VECRM internal doctype fields use the `vecrm_` prefix (`vecrm_phone`,
`vecrm_email`, `vecrm_base_city`, `vecrm_account_status`). When VECRM
Auth ships in S25 and the portal needs employee fields on responses,
portal-facing API responses translate to reader-friendly keys
(`full_name`, `base_city`, `is_active` as a boolean projection of
`vecrm_account_status`).

This is a deliberate API-boundary translation, NOT a coincidental
mismatch — the portal does not learn VECRM's internal prefixing
convention, so future internal renames don't break the portal.

Sub-A does not exercise this convention (its `/api/me` returns only the
Frappe User email). The convention is documented now so S25 implements
the employee-aware `/api/me` variant consistently.

## 9. Styling convention

- Per-page `<style>` blocks holding a CSS string, with CSS variables
- No Tailwind utility classes in JSX (Tailwind v4 is installed but
  unused in existing pages — match this until a future S session
  deliberately migrates the convention)
- Canonical class names (see leads/inquiries/travel-voucher pages):
  `.page`, `.page-header`, `.page-title`, `.page-sub`, `.filter-btn`,
  `.btn-primary`, `.btn-secondary`, `.error-box`, `.empty`, `.field`,
  `.field-label`, `.field-value`, `.skel`, `.action-slot`
- CSS variables: `--color-vemio-*`, `--font-display`, `--font-mono`

## 10. VPS-discipline convention (standing)

Default: operator-driven VPS commands. The dispatcher hands the operator
the exact ssh/scp/docker/bench blocks; the operator runs them.

Lifts: per-dispatch authorization required. A lift MUST include explicit
bookends — start condition, end condition, scope-of-lift, and
inheritance rule. See OBS-S24-C in the S24-close handover.

DISPATCH-S24-A2-IMPLEMENTATION-v3 was a lifted dispatch (additive
deploys allowed, bookended to that dispatch only). All subsequent
dispatches default back to operator-driven unless they explicitly lift
again with new bookends.

## 11. Auth posture (Sub-A interim, S25 target)

**Sub-A interim:**

- The portal is Admin-only — only Ajay (Frappe User
  `ajay@vinayenterprises.co.in`) can log in, via S23 PR #4's SSR cookie
  hydration.
- The create form requires explicit submitter selection (employee
  picker via `/api/employees`).
- No role-based UI variation. The detail view's action-panel slots are
  all rendered as placeholders.
- Implementation note: the action-panel slots are plain `"use client"`
  page markup — `<div data-slot=...>` elements with a `display: none`
  CSS rule — NOT server-component splits. There is no server-component
  split anywhere in this portal; every page is a `"use client"`
  component that fetches via `useEffect`. Downstream phases fill the
  slot divs in place (OBS-S24-K).

**S25 PD-S25-VECRM-AUTH target:**

- Phone + 6-digit PIN auth path (primary for Sales Reps in the field)
- Email + password auth path (primary for office-based HR / Sales Head)
- Both paths land on the same VECRM Employee identity
- Session→employee resolution drives create-form pre-fill, list-view
  default filter, and action-panel slot visibility
- Sub-A's BFF routes and pages absorb the change with minimal
  modification — the structure was designed for this transition

When S25 ships, this section is updated to reflect the realized posture.
