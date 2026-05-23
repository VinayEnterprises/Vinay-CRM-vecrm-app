# S25 A1 Recon Report — PD-S25-VECRM-AUTH

**Dispatch:** DISPATCH-S25-A1 · Phase A (recon) · executor Claude Code
**Status:** R1, R2 complete (local recon). R3, R4 require operator-run VPS
output. R5 partially reconstructed (see tooling note). R6 synthesised
from what is available; items pending R3/R4 are marked.

> **Tooling note:** `conversation_search` is **not available** to this
> executor. Steps 4 (VEMIO Graph history) and 5 (cross-session auth
> search) cannot be run via that tool. R4/R5 below cover what is
> reconstructable from this conversation + the in-repo handover docs;
> genuinely older-session history (pre-S23) is a gap a dispatcher with
> conversation_search must fill.

---

## R1. VECRM Employee — current shape

`vecrm/vecrm/doctype/vecrm_employee/vecrm_employee.json`

- `autoname`: **`field:vecrm_phone`** · no `naming_rule` · `allow_rename: 0`
- `links: []` · `actions: []` · `permissions`: **System Manager only**
  (create/read/write/email/print/share; delete 0). No VECRM Admin row.

| field | type | reqd | unique | notes |
|---|---|---|---|---|
| `employee_name` | Data | 1 | — | display name |
| `vecrm_phone` | Data | 1 | **1** | `set_only_once`; autoname key; label "Phone (OTP Identity)" |
| `vecrm_email` | Data | 0 | — | `options: Email`; label "Email (Magic-Link / Notifications)" |
| `role` | Select | 1 | — | Admin / Sales Head / HR / Sales Rep / Field Engineer / Head of Engineers |
| `vecrm_base_city` | Data | 1 | — | validated against Rate Card |
| `reporting_approver` | Link→VECRM Employee | 0 | — | self-referential; unused so far |
| `vecrm_account_status` | Select | 1 | — | Active / Suspended, default Active |

**No credential fields** — no `pin`, `password`, `hash`, `secret`, and
**no `linked_user`**. (v2 of the S24 A2 dispatch proposed an
`Employee.linked_user → Frappe User` field; v3 stripped it and it never
landed — the JSON confirms its absence.)

Controller (`vecrm_employee.py`) — minimal, **no auth/session logic**:
- `validate()` → `_validate_phone_immutable` (phone is "the auth
  identity", blocked from change post-create — defense-in-depth over
  `set_only_once`) + `_validate_base_city_in_rate_card`.
- No `before_insert` / `before_save` / `on_update`.

⚠️ **Stale-label note:** field labels say "OTP Identity" and
"Magic-Link", and the controller comment calls phone "the auth
identity" — the doctype was designed *anticipating* phone-based auth,
but the operator's S25 decision (see R5) is **phone+PIN / email+password,
explicitly NOT OTP**. Labels are stale relative to the live decision;
A2 should refresh them.

Production-data probe (operator-run — see Operator Command Set §A):
expected 2 rows (Test Sales Rep, Test HR Approver), both
`vecrm_account_status=Active`, both Ahmedabad, **neither with a
`vecrm_email` value** (per S24 §9). Confirm and flag any drift.

## R2. Portal auth shim — current behaviour (S23 PR #4 + S24 PR #5)

- **No `middleware.ts`. No `app/(login)/` route group.** (The dispatch's
  Step 2 paths assumed both — neither exists.)
- Auth-relevant files: `app/api/auth/{login,logout,me}/route.ts`,
  `app/api/me/route.ts` (S24), `lib/auth-ssr.ts`, `app/layout.tsx`,
  `app/components/AppShell.tsx`, `app/useAuth.ts`, `app/LoginForm.tsx`.

**Mechanism — pure Frappe-session passthrough. The portal has no auth of
its own:**
- `lib/auth-ssr.ts` `getFrappeUser()` — server-side; reads the `sid`
  cookie; **round-trips to Frappe** (`/api/method/frappe.auth.get_logged_user`)
  on every request. It does **not** trust a local signature.
- Login: `useAuth.login(usr,pwd)` → `POST /api/auth/login` → Frappe
  `/api/method/login` (a **Frappe User** email + password) → Frappe
  issues the `sid` cookie → forwarded to the browser.
- `app/layout.tsx` resolves the user via `getFrappeUser()` and passes it
  to `AppShell`, which renders `<LoginForm>` if null, else the app.
- Cookie: **`sid`** (Frappe's). The portal sets/reads **no cookie of its
  own**.

**Critical R2 answers:**
- *Does the shim talk to Frappe each request?* **Yes** — `getFrappeUser`
  round-trips every request. No local session, no signed local cookie.
- *What is "Admin-only" in code?* **Emergent, not enforced.** There is
  **no role-check and no name-check anywhere.** The portal accepts any
  valid Frappe `sid`; only `ajay@` has Frappe-User credentials, so only
  `ajay@` can obtain one. "Admin-only" = "only one Frappe User exists."

**Implication:** VECRM Auth must give the portal its *own* auth, because
Sales Reps / HR are **not** Frappe Users and cannot get a Frappe `sid`
via `/api/method/login`. The shim's **shape** (server-resolve user →
prop to AppShell) can survive; what changes is the login route, the
session source, and what backs `getFrappeUser()`.

## R3. Frappe v16 built-in auth surfaces — OPERATOR-RUN VPS REQUIRED

Cannot be read locally (framework code lives in the container). The
exact commands are in Operator Command Set §B. The questions R3 must
answer:

- `LoginManager` (frappe/auth.py) — method shapes; **does it accept an
  arbitrary identifier field, or is it hardcoded to `email`/`username`
  on `tabUser`?** (This is the make-or-break for option (i).)
- Password hashing scheme (passlib — bcrypt / pbkdf2 / argon2).
- Native phone-as-username support?
- Session cookie set (`sid`, `user_id`, `system_user`, `full_name`).
- Built-in rate-limit / lockout (`tabUser.login_after`, `max_login_attempts`)?
- Built-in forgot-password flow + how it sends email.
- `site_config.json` auth-relevant keys (`disable_signup`,
  `enable_two_factor_auth`, mail keys, etc.).

**R3 stays OPEN until operator returns §B output.**

## R4. Microsoft Graph wiring (VEMIO precedent) — GAP

`conversation_search` unavailable to this executor, so VEMIO's Graph
history cannot be searched here. What is needed (a dispatcher with
conversation_search, or the operator, must supply):
- Where VEMIO's Graph credentials live (env / site_config / secrets).
- VEMIO's `from:` address; whether the Graph app-registration is
  VEMIO-scoped or tenant-wide (reusable by VECRM with a different `from:`?).
- VEMIO's Graph pitfalls (userMemory mentions an S63/PD46 "stale gate").

VECRM's current mail config: operator-run check in §C.

**Critical question for Phase B:** can VECRM reuse VEMIO's Graph
app-registration with a different `from:`, or does it need its own?
**R4 stays OPEN.**

## R5. Past-session auth context — reconstructed from this conversation

`conversation_search` unavailable; the following is reconstructed from
this conversation's content + in-repo handover docs. Pre-S23 history is
a gap.

- ⚠️ **PRIOR-DECISION (S24, DISPATCH-S24-A2-IMPLEMENTATION-v3 §0.2):**
  the operator's amended auth design is **two co-equal paths — phone +
  6-digit PIN, and email + password — a single VECRM Employee identity;
  hashed PIN/password; rate limiting; lockout; email-based forgot-PIN.
  OTP was explicitly rejected** (per-message cost, internal-only usage).
  This is a settled decision — do not re-litigate.
- ⚠️ **PRIOR-DECISION (S24 v3 §0.1):** the v2 design's
  `Employee.linked_user → Frappe User` bridge was **explicitly rejected**
  — reasoning: it "solved the wrong problem; works for Admin-shaped
  users but not Sales Reps, because reps have no Frappe Users."
  **This is strong signal against option (i)** (Frappe built-in auth,
  1:1 Employee↔User) — option (i) would require minting a Frappe User
  per Employee, which S24's reasoning argued against. Phase B must weigh
  this explicitly rather than re-deciding silently.
- The portal auth shim (S23 PR #4 "SSR cookie hydration") was built to
  kill PD-S22-LOADING-FLASH — its purpose was UX, not real auth; it
  always was a Frappe-`sid` passthrough placeholder.
- S24 Sub-A / Sub-B / Lead-create all shipped **"Admin-only" interim**
  surfaces explicitly gated on PD-S25-VECRM-AUTH to make them real for
  non-Admin users. `docs/portal-conventions.md §11` documents the
  interim-vs-S25-target auth posture.

## R6. Recon-derived constraints

- **C1.** VECRM Employee has **zero credential fields** and no
  `linked_user`. Options (ii)/(iii) require adding credential storage —
  either fields on Employee (`pin_hash`, `password_hash`,
  `failed_login_count`, `locked_until`, …) or a separate Credential
  doctype.
- **C2.** The portal shim is a Frappe-`sid` passthrough that round-trips
  every request; **no local session, no middleware, no role-gate.**
  VECRM Auth changes: `app/api/auth/login/route.ts`, the resolver
  `lib/auth-ssr.ts`, and `/api/me`. The server-resolve→AppShell-prop
  shape can be kept.
- **C3.** Frappe `LoginManager` phone-identifier support — **PENDING R3**.
  If hardcoded to `email`/`username`, option (i) needs monkey-patching.
- **C4.** Graph reuse vs new app-registration — **PENDING R4**. 2–4h
  effort delta depending.
- **C5.** ⚠️ S24 already rejected the Frappe-User-per-Employee bridge
  (R5). Option (i) is in tension with a settled prior decision; Phase B
  must justify any recommendation of (i) against C5, not around it.
- **C6.** Operator pre-commitments (Guard H) the recommendation must
  honour: compare **all three** options; **co-equal** phone+PIN /
  email+password on a **single** login screen; forgot-PIN is
  **MVP-full-pre-DLT, email-based**.
- **C7.** `vecrm_email` is currently **optional and non-unique**.
  Email+password login requires it to be **present and unique** for any
  email-login user. The 2 test employees have no `vecrm_email` today —
  A2 must add `unique: 1` and a population path. Phone-login users can
  leave it null.
- **C8.** `vecrm_phone` is `unique` + `set_only_once` + autoname key +
  immutability-guarded — already a solid phone-login identity; no schema
  change needed for the phone path.
- **C9.** `require_type_annotated_api_methods=true` — every new auth
  `@frappe.whitelist()` method must be fully type-annotated.

---

## Operator Command Set (read-only VPS — operator-driven, no lift)

**§A — VECRM Employee production data** (note: real field is
`employee_name`, NOT `vecrm_full_name` which the dispatch's draft SQL
used — OBS-S24-A):
```
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute frappe.db.sql --args '"'"'["SELECT name, vecrm_phone, vecrm_email, employee_name, vecrm_account_status, vecrm_base_city FROM \`tabVECRM Employee\` ORDER BY creation", null, true]'"'"''
```

**§B — Frappe built-in auth surfaces:**
```
ssh root@217.216.58.117 'docker exec vecrm-backend-1 sed -n "1,120p" /home/frappe/frappe-bench/apps/frappe/frappe/auth.py'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 grep -nE "def (login|authenticate|check_password|reset_password|validate_ip_address)" /home/frappe/frappe-bench/apps/frappe/frappe/auth.py'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 grep -rn "passlib\|CryptContext" /home/frappe/frappe-bench/apps/frappe/frappe/utils/password.py'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 cat /home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json'
```

**§C — VECRM mail config:**
```
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.client.get_list" --kwargs "{\"doctype\": \"Email Account\", \"fields\": [\"name\", \"email_id\", \"service\"]}"'
```

---

## Phase A close status

R1, R2, R6(local-derivable) **complete**. R3, R4 **OPEN** pending the
§A–§C operator output. R5 reconstructed-from-this-conversation; pre-S23
history is a `conversation_search` gap. Once operator returns §A–§C,
this executor finalises R3, R4, and the PENDING C3/C4 constraints —
then Phase A closes and the dispatcher authors Phase B.
