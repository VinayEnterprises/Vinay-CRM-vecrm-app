# VECRM-DEPENDENCY-S28-CLOSE

**Supersedes:** `VECRM-DEPENDENCY-S27-CLOSE.md`
**Generated:** 2026-05-24 (S28 close)

---

## §1 — Repos

| Repo | Path | Purpose | Current HEAD |
|---|---|---|---|
| `vecrm` | `~/Documents/GitHub/vecrm` → `git@github.com:VinayEnterprises/Vinay-CRM-vecrm-app.git` | Frappe v16 custom app | `955f7ae` (advances on S28 close docs merge) |
| `vecrm-portal` | `~/Documents/GitHub/vecrm-portal` → `git@github.com:VinayEnterprises/vecrm-portal.git` | Next.js 16 / React 19 portal | `8f7c1b7` |
| `frappe_docker` (upstream) | `/opt/vecrm/` on VPS only | Build context | upstream tracking, not modified |

---

## §2 — Architectural locks (PERMANENT)

### Pre-S28 permanent locks (carried forward — 27 at S27 close)

- **VECRM-L8** — voucher_counter.py canonical path + sha (`91556a7d07...` as of S27)
- **VECRM-L11** — port allocator semantics
- **VECRM-L13** — branch-first commits, squash-merge + branch deletion
- **VECRM-L17** — Counter increment via `last_value` column
- **VECRM-L18** — bench console module-level code (VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION)
- **VECRM-L19** — VPS-side destructive ops require operator confirmation
- **VECRM-L20** — Frappe lifecycle order (autoname, in_create, etc)
- **VECRM-L21** — Frappe session persistence patterns
- **VECRM-L22** — Atomic schema migrations with assertions + paired rollback file
- **VECRM-L23** — Narrow build context per worker
- **VECRM-L24** — File-scope scp only (no `scp -r` for file edits)
- **VECRM-L25** — Timing math before bug-call
- **VECRM-L26** — Always `\d <table>` (DESCRIBE) before SQL probe
- **VECRM-L27** — Verify history/inventory at every layer-transition checkpoint
- **VECRM-LOCK-S13-VENDOR-NO-GIT** — Vendor directory must not contain `.git`
- **VECRM-LOCK-AUTONAME-HYGIENE** — Frappe autoname patterns
- **VECRM-LOCK-FILE-DELIVERY-NOT-PASTE** — Files via attached artifacts, not pasted into chat
- **VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER** — In-create flag pre-set, autoname pre-set
- **VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE** — Session writes via `frappe.local.session.data` + commit
- **VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE** — Decode dynamic route params explicitly
- **VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE** — Use Data fieldtype, never Password
- **VECRM-LOCK-PORTAL-USER-ROLES** — Role list on portal users
- **VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE** — Pre-merge probe pattern
- **VECRM-LOCK-VPS-DESTRUCTIVE-OPS** — Operator-only destructive operations
- **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** (S27) — Auth principal is shared `vecrm-portal@vinayenterprises.co.in`; per-rep identity in `VECRM Employee` keyed by phone
- **VECRM-LOCK-VPS-PATH-CONVENTIONS** (S27) — `/opt/vecrm/` paths
- **VECRM-LOCK-CONTAINERFILE-SHA-MAINTENANCE** (S27) — Update Containerfile sha-gate when canonical voucher_counter.py changes
- **VECRM-LOCK-VEMIO-EMAIL-PATTERN** (S27) — VECRM portal email mirrors Vemio's portal-side Graph fetch pattern
- **VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE** (S27) — Dispatch code samples are illustrative; existing code wins

### S28-promoted permanent locks (NEW)

- **VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY** — Public-auth paths (paths a logged-out user must reach without short-circuiting to LoginForm) declared as hardcoded `string[]` at module top-level with explicit `Array.includes(pathname)` check. NOT `startsWith`, NOT regex. Keeps the auth-trust boundary auditable.

**Total permanent locks at S28 close: 28** (27 at S27 close + 1 promoted this session).

### Lock applications observed this session

- **VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE** held without exception across **4 build dispatches** with code samples this session (BACKEND-API path divergence, PORTAL-BFF helper-signature divergence, PORTAL-UI file-layout divergence, EMAIL-TEMPLATE styling divergence). Now load-bearing for any multi-dispatch session with code samples.
- **VECRM-LOCK-VEMIO-EMAIL-PATTERN** held cleanly in PR #11; vemio-dashboard `lib/email.js` pattern transferred 1:1.
- **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** continues load-bearing for the entire reset flow.
- **VECRM-LOCK-FILE-DELIVERY-NOT-PASTE** held across all 8 PRs (all commit messages + PR bodies via `/tmp/*.txt` files).
- **VECRM-L13** held across all 8 PRs.

---

## §3 — Module dependency graph (high-level)

```
vecrm-portal (Next.js, Vercel)
├── app/                                    (auth-related at app/ root; no app/(auth) group)
│   ├── LoginForm.tsx                       S25, S26 → S27 PR #10 (UA polish) → S28 PR #14 (mode toggle)
│   ├── useAuth.ts                          S25
│   ├── useTheme.ts                         S22
│   ├── layout.tsx                          S22
│   ├── page.tsx                            S22
│   ├── set-password/page.tsx               S28 PR #14 (NEW — token-accept page)
│   ├── set-pin/page.tsx                    S28 PR #14 (NEW)
│   ├── components/                         (shared layout chrome)
│   │   ├── AppShell.tsx                    S22 → S28 PR #14 (PUBLIC_AUTH_PATHS whitelist) ★ NEW LOCK
│   │   ├── TopBar.tsx                      S22
│   │   ├── MobileNav.tsx                   S22
│   │   ├── StatusPill.tsx                  S22
│   │   ├── PriorityBadge.tsx               S22
│   │   ├── ThemeToggle.tsx                 S22
│   │   └── auth/                           ★ NEW SUBDIRECTORY S28 PR #14
│   │       ├── ForgotPasswordForm.tsx      S28 PR #14
│   │       ├── ForgotPinForm.tsx           S28 PR #14
│   │       ├── SetPasswordForm.tsx         S28 PR #14
│   │       └── SetPinForm.tsx              S28 PR #14
│   ├── api/auth/
│   │   ├── login/route.ts                  S25, S26
│   │   ├── login-pin/route.ts              S26
│   │   ├── logout/route.ts                 S25 → S27 PR #19
│   │   ├── forgot-password/route.ts        S28 PR #13 (NEW)
│   │   ├── forgot-pin/route.ts             S28 PR #13 (NEW)
│   │   └── complete-reset/route.ts         S28 PR #13 (NEW)
│   ├── api/me/route.ts                     S26
│   ├── leads/                              S25 + S27 PR #20
│   ├── inquiries/                          S20
│   └── travel-vouchers/                    S22
├── lib/
│   ├── frappe.ts                           S25 (API client) — used by S28 BFF routes
│   ├── auth-ssr.ts                         S23 (server-side getFrappeUser)
│   ├── email.js                            S28 PR #11 (NEW) — mirrors vemio-dashboard/lib/email.js
│   └── email-templates/                    ★ NEW SUBDIRECTORY S28 PR #12
│       ├── shared.ts                       S28 PR #12 (renderEmailLayout, renderPrimaryButton, escapeHtml, escapeAttr)
│       ├── password-reset.ts               S28 PR #12
│       └── pin-reset.ts                    S28 PR #12

vecrm (Frappe v16 app)
├── vecrm/api.py                            Core API methods
│   ├── login_with_password                 S25
│   ├── login_with_pin                      S26
│   ├── vecrm_logout                        S25 → S27 PR #19
│   ├── create_lead                         S25 → S27 PR #20
│   ├── convert_lead_to_inquiry             S20
│   ├── request_password_reset              S28 PR #22 (NEW) + PR #23 (delivery_email) + PR #24 (display_name)
│   ├── request_pin_reset                   S28 PR #22 (NEW) + PR #23 + PR #24
│   ├── complete_password_reset             S28 PR #22 (NEW)
│   ├── complete_pin_reset                  S28 PR #22 (NEW)
│   ├── _make_reset_response (helper)       S28 PR #22 + PR #23 (delivery_email default) + PR #24 (docstring)
│   ├── _count_recent_reset_tokens (helper) S28 PR #22
│   ├── _create_reset_token_row (helper)    S28 PR #22
│   └── _consume_reset_token (helper)       S28 PR #22
├── vecrm/vecrm/utils/                      ★ Subdirectory established S25 (roles.py); S28 adds auth_reset.py
│   ├── roles.py                            S25
│   └── auth_reset.py                       S28 PR #22 (NEW) — pure crypto: generate_token, hash_token, constant_time_equals
├── vecrm/vecrm/doctype/
│   ├── vecrm_voucher_counter/              S15 (canonical allocator)
│   ├── vecrm_employee/                     S20
│   ├── vecrm_rate_card/                    S20
│   ├── vecrm_rate_card_city/               S20
│   ├── vecrm_user_audit_log/               S20
│   ├── vecrm_auth_audit_log/               S26 — extended S28 with auth.reset.* vocabulary
│   ├── vecrm_auth_reset_token/             S27 PR #21 — first production use S28
│   ├── vecrm_inquiry/                      S20
│   ├── vecrm_inquiry_audit_log/            S20
│   ├── vecrm_lead/                         S20 → S27 PR #20
│   ├── vecrm_assignment_ledger_entry/      S20
│   ├── vecrm_assignment_log_row/           S20
│   ├── vecrm_expense_voucher/              S20
│   ├── vecrm_expense_line/                 S20
│   ├── vecrm_travel_voucher/               S20
│   ├── vecrm_visit_line/                   S20
│   └── vecrm_voucher_audit_log/            S20
├── vecrm/patches/
│   ├── v1_1/                               S20-S26 (8 forward + 8 rollback)
│   └── v1_2/                               S27 (1 forward + 1 rollback)
└── vecrm/vecrm/voucher_counter.py          VECRM-L8 canonical (no change S28)
```

S28-introduced surfaces (★ marked):
- New portal subdirectory `vecrm-portal/app/components/auth/` (4 components)
- New portal subdirectory `vecrm-portal/lib/email-templates/` (3 modules)
- New portal route group `vecrm-portal/app/set-password/` + `app/set-pin/` (token-accept pages)
- New backend module `vecrm/vecrm/utils/auth_reset.py` (pure-crypto helpers)
- New AppShell whitelist mechanism (PUBLIC_AUTH_PATHS) — governed by new lock

---

## §4 — Schema dependency map

### tabVECRM Employee (S20)

Used by: VECRM Lead, VECRM Inquiry, VECRM Assignment Ledger Entry, VECRM Expense Voucher, VECRM Travel Voucher, VECRM Auth Reset Token, **vecrm/api.py reset methods (S28)**

S28 read patterns confirmed:
- `frappe.db.get_value("VECRM Employee", {"vecrm_email": email}, "name")` — password reset lookup
- `frappe.db.get_value("VECRM Employee", normalized_phone, "name")` — PIN reset lookup
- `frappe.get_doc("VECRM Employee", employee_name)` — for `vecrm_account_status`, `employee_name` (display), `vecrm_email`, `failed_*_attempts`, `locked_until`, `pin_locked_until`, `password_hash`, `pin_hash`

Naming clash documented this session (PR #24): `name` field is autoname = phone; `employee_name` is the display name. Multiple places in api.py read `employee_doc.employee_name` as the display name (lines 476, 546, 618, 653, and now post-PR #24 the two reset write sites at 840 and 914).

### tabVECRM Auth Audit Log (S26)

Used by: vecrm.api login/logout flows, **S28 reset flow (new auth.reset.* vocabulary)**

Event vocabulary (post-S28):
- Login: `auth.login.success`, `auth.login.fail`, `auth.login.locked` (S26)
- Logout: `auth.logout` with `path={password,pin,NULL}` (S26+S27)
- Reset (S28 new vocabulary, actively emitting):
  - `auth.reset.requested` (any reset request; employee NULL on no-match path per no-enumeration)
  - `auth.reset.consumed` (successful credential write)
  - `auth.reset.expired` (TTL exceeded)
  - `auth.reset.invalid_token` (with `reason` discriminator: NULL, `already_consumed`, `wrong_reset_for`)
  - `auth.reset.rate_limited`

Audit row columns (all populated by `_audit_auth` helper):
- `event`, `employee` (NULL on no-match), `identifier` (email/phone), `path` (password/pin), `reason` (NULL or discriminator), `ip_address`, `user_agent`, `extra` (JSON), `creation`

### tabVECRM Auth Reset Token (S27)

First production use: S28. Rows: variable (consumed + expired tokens retained for audit forensics until manual cleanup).

Used by: vecrm.api reset methods (read for validation; write for mint + consume).

Key fields: `token_hash` (sha256, UNIQUE, length 64), `employee` (Link), `reset_for` (Select: password|pin), `expires_at`, `consumed_at` (NULL until consume), `ip_address`

Permissions: System Manager only. Portal users access via `allow_guest=True` whitelist API methods that mediate read/write.

### tabVECRM Lead (S20)

S27 PR #20 added: `creating_employee` (Link to VECRM Employee, nullable, populated by `create_lead` API from session.data)

15 rows at S28 close (was 14 at S27; +1 from PR #25 §2 audit smoke). All attributed to `+91-9327547536` (Ajay). Per-rep scoping logic still deferred to PD-S28-LEAD-SCOPING-CUTOVER (P1 for S29).

### tabVECRM Voucher Counter (S15)

Allocator. Increment column: `last_value`. NEVER NULL. Lookup pattern: `series_code = "<prefix>-<fiscal_year>"`.

Current state (no change S28):
- EV-26-27=12, INQ-26-27=12, LEAD-26-27=15 (+1 from audit smoke), TV-26-27=94, TV-27-28=14

---

## §5 — Build / deploy dependencies

| Dependency | Lives at | Purpose |
|---|---|---|
| `vecrm` git repo on Mac | `~/Documents/GitHub/vecrm` | Authoring source |
| `vecrm` git repo origin | github.com/VinayEnterprises/Vinay-CRM-vecrm-app | Canonical source of truth |
| `vecrm-portal` git repo on Mac | `~/Documents/GitHub/vecrm-portal` | Authoring source |
| `vecrm-portal` git repo origin | github.com/VinayEnterprises/vecrm-portal | Canonical |
| Vendored vecrm on VPS | `/opt/vecrm/vecrm-src/` | Build input (rsync'd from Mac main) |
| Containerfile | `/opt/vecrm/images/custom/Containerfile` | Build definition (NOT in any tracked repo — PD-S28-CONTAINERFILE-TRACKED still open) |
| apps.json secret | `/opt/vecrm/apps.json` | BuildKit secret for apps definition |
| vecrm-portal on Vercel | `https://app.vinayenterprises.co.in` | Auto-deploy on push to main |
| Frappe site | `crm.vinayenterprises.co.in` running on Contabo VPS | Backend |
| MariaDB volume | Docker named volume on VPS | Schema + data persistence |

No build/deploy dependencies changed during S28. Four backend deploys (PR #22, #23, #24 + S27 PR #21 carryover) all used PD-S27-DEPLOY-RUNBOOK cleanly; four portal deploys (PR #11, #12, #13, #14) via Vercel auto-deploy.

---

## §6 — External integrations

| Service | Used by | Auth | Config | S28 status |
|---|---|---|---|---|
| Azure AD (vemio-email-sender app reg) | vecrm-portal Graph email send | Client-credentials OAuth | `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` (Vercel env vars) | **ACTIVE** — first VECRM use this session |
| Microsoft Graph (`/users/{id}/sendMail`) | vecrm-portal reset flow | Bearer token from above | `GRAPH_SENDER_NOREPLY_VECRM = DoNotReply@vinayenterprises.co.in` | **ACTIVE** — N reset emails delivered this session |
| M365 Outlook (mailbox) | Receives reset emails | M365 tenant ownership | `vinayenterprises.co.in` domain with SPF/DKIM/DMARC verified | **ACTIVE** — DNS auth headers assumed pass-pass-pass from PR #11 smoke evidence |

Quota / rate state at S28 close: well below any Graph throttling thresholds. The `vemio-email-sender` app reg is shared with vemio-dashboard; total send volume across both projects is operationally small.

---

## §7 — Docs structure (at S28 close)

```
docs/
├── architectural-locks/                              28 lock files at S28 close (was 27 at S27)
│   ├── VECRM-L8.md ... VECRM-L27.md
│   ├── VECRM-LOCK-AUTONAME-HYGIENE.md
│   ├── VECRM-LOCK-FILE-DELIVERY-NOT-PASTE.md
│   ├── VECRM-LOCK-FRAPPE-LIFECYCLE-ORDER.md
│   ├── VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE.md
│   ├── VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE.md
│   ├── VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE.md
│   ├── VECRM-LOCK-PORTAL-USER-ROLES.md
│   ├── VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE.md
│   ├── VECRM-LOCK-VPS-DESTRUCTIVE-OPS.md
│   ├── (S27-era locks)
│   └── VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY.md   ★ NEW S28
├── dispatches/
│   ├── PD-S28-AUTH-RESET-INFRA-recon-findings*.md
│   ├── PD-S28-AUTH-RESET-SCHEMA-dispatch.md
│   ├── PD-S28-AUTH-RESET-BACKEND-API-dispatch.md
│   ├── PD-S28-AUTH-RESET-EMAIL-MECHANISM-dispatch.md
│   ├── PD-S28-AUTH-RESET-PORTAL-BFF-dispatch.md
│   ├── PD-S28-AUTH-RESET-PORTAL-UI-dispatch.md
│   ├── PD-S28-AUTH-RESET-EMAIL-TEMPLATE-dispatch.md
│   ├── PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE-dispatch.md
│   └── PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md   ★ NEW S28 (PR #25 artifact)
├── handovers/
│   ├── PD-S26-CLOSE-HANDOVER.md
│   ├── PD-S27-CLOSE-HANDOVER.md
│   ├── PD-S28-CLOSE-HANDOVER.md                        ★ NEW S28
│   ├── VECRM-PENDENCY-S26-CLOSE.md
│   ├── VECRM-PENDENCY-S27-CLOSE.md
│   ├── VECRM-PENDENCY-S28-CLOSE.md                     ★ NEW S28
│   ├── VECRM-DEPENDENCY-S26-CLOSE.md
│   ├── VECRM-DEPENDENCY-S27-CLOSE.md
│   ├── VECRM-DEPENDENCY-S28-CLOSE.md                   ★ NEW S28 (this doc)
│   ├── S27-OPENER-PROMPT.md
│   ├── S28-OPENER-PROMPT.md
│   └── PD-S29-OPENER.md                                ★ NEW S28
├── operating-patterns/
│   ├── cold-check-template.md
│   └── mariadb-probe.md
├── runbooks/
│   ├── PD-S27-DEPLOY-RUNBOOK.md                        (unchanged S28; held cleanly across 4 backend deploys)
│   └── rebuild/
├── session-handovers/                                  S23-S25 historical
└── session-scripts/                                    S20 historical
```

---

## §8 — Cross-references

- Close handover: `docs/handovers/PD-S28-CLOSE-HANDOVER.md`
- Pendency: `docs/handovers/VECRM-PENDENCY-S28-CLOSE.md`
- Deploy runbook: `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md` (still canonical)
- S29 opener: `docs/handovers/PD-S29-OPENER.md`
- Security audit findings: `docs/dispatches/PD-S28-AUTH-RESET-SECURITY-REVIEW-findings.md` — **referenceable for any future auth work**
- New lock: `docs/architectural-locks/VECRM-LOCK-PUBLIC-AUTH-PATHS-HARDCODED-ARRAY.md`

**End of dependency map.**
