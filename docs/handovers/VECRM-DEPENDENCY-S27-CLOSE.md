# VECRM-DEPENDENCY-S27-CLOSE

**Supersedes:** `VECRM-DEPENDENCY-S26-CLOSE.md`
**Generated:** 2026-05-24 (S27 close)

---

## §1 — Repos

| Repo | Path | Purpose | Current HEAD |
|---|---|---|---|
| `vecrm` | `~/Documents/GitHub/vecrm` → `git@github.com:VinayEnterprises/Vinay-CRM-vecrm-app.git` | Frappe v16 custom app | `6d46b0d` |
| `vecrm-portal` | `~/Documents/GitHub/vecrm-portal` → `git@github.com:VinayEnterprises/vecrm-portal.git` | Next.js 16 / React 19 portal | `8540794` |
| `frappe_docker` (upstream) | `/opt/vecrm/` on VPS only | Build context | upstream tracking, not modified |

---

## §2 — Architectural locks (PERMANENT)

### Pre-S27 permanent locks (carried forward)

- **VECRM-L8** — voucher_counter.py canonical path + sha (`91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9` as of S27)
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

### S27-promoted permanent locks (NEW)

- **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** — Auth principal is shared `vecrm-portal@vinayenterprises.co.in`; per-rep identity in `VECRM Employee` keyed by phone
- **VECRM-LOCK-VPS-PATH-CONVENTIONS** — `/opt/vecrm/` is frappe_docker; `/opt/vecrm/vecrm-src/` is vendored vecrm
- **VECRM-LOCK-CONTAINERFILE-SHA-MAINTENANCE** — Update Containerfile sha-gate when canonical voucher_counter.py changes
- **VECRM-LOCK-VEMIO-EMAIL-PATTERN** — VECRM portal email-send mirrors Vemio's portal-side Graph fetch pattern; Frappe stays SMTP-free

**Total permanent locks at S27 close: 27** (23 pre-S27 + 4 promoted this session).

---

## §3 — Module dependency graph (high-level)

```
vecrm-portal (Next.js, Vercel)
├── app/(auth)/
│   ├── login/page.tsx                  S25, S26 → S27 PR #10 (UA polish)
│   ├── set-password/page.tsx           [S28 PD-S28-AUTH-RESET-PORTAL-UI]
│   └── set-pin/page.tsx                [S28 PD-S28-AUTH-RESET-PORTAL-UI]
├── app/api/auth/
│   ├── login/route.ts                  S25, S26
│   ├── login-pin/route.ts              S26
│   ├── logout/route.ts                 S25 → S27 PR #19 (path discriminator)
│   ├── forgot-password/route.ts        [S28 PD-S28-AUTH-RESET-PORTAL-BFF]
│   ├── forgot-pin/route.ts             [S28 PD-S28-AUTH-RESET-PORTAL-BFF]
│   └── complete-reset/route.ts         [S28 PD-S28-AUTH-RESET-PORTAL-BFF]
├── app/leads/
│   ├── page.tsx                        [S28+ list page TBD]
│   └── new/page.tsx                    S25 → S27 PR #20 backed
├── components/auth/
│   ├── LoginForm.tsx                   S25, S26 → S27 PR #10
│   ├── ForgotPasswordForm.tsx          [S28 PD-S28-AUTH-RESET-PORTAL-UI]
│   ├── ForgotPinForm.tsx               [S28]
│   ├── SetPasswordForm.tsx             [S28]
│   └── SetPinForm.tsx                  [S28]
├── lib/
│   ├── frappe.ts                       S25 (API client)
│   ├── email.js                        [S28 PD-S28-AUTH-RESET-EMAIL-MECHANISM] — mirrors vemio-dashboard/lib/email.js
│   └── email-templates/
│       ├── shared.ts                   [S28 PD-S28-AUTH-RESET-EMAIL-TEMPLATE]
│       ├── password-reset.ts           [S28]
│       └── pin-reset.ts                [S28]
└── ...

vecrm (Frappe v16 app)
├── vecrm/api.py                        Core API methods
│   ├── login_with_password             S25
│   ├── login_with_pin                  S26
│   ├── vecrm_logout                    S25 → S27 PR #19 (path discriminator)
│   ├── create_lead                     S25 → S27 PR #20 (creating_employee)
│   ├── convert_lead_to_inquiry         S20
│   ├── request_password_reset          [S28 PD-S28-AUTH-RESET-BACKEND-API]
│   ├── request_pin_reset               [S28]
│   ├── complete_password_reset         [S28]
│   └── complete_pin_reset              [S28]
├── vecrm/utils/auth_reset.py           [S28 PD-S28-AUTH-RESET-BACKEND-API]
├── vecrm/vecrm/doctype/
│   ├── vecrm_voucher_counter/          S15 (canonical allocator)
│   ├── vecrm_employee/                 S20
│   ├── vecrm_rate_card/                S20
│   ├── vecrm_rate_card_city/           S20
│   ├── vecrm_user_audit_log/           S20
│   ├── vecrm_auth_audit_log/           S26
│   ├── vecrm_auth_reset_token/         S27 PR #21 (PD-S28-AUTH-RESET-SCHEMA) — NEW
│   ├── vecrm_inquiry/                  S20
│   ├── vecrm_inquiry_audit_log/        S20
│   ├── vecrm_lead/                     S20 → S27 PR #20 (creating_employee column)
│   ├── vecrm_assignment_ledger_entry/  S20
│   ├── vecrm_assignment_log_row/       S20
│   ├── vecrm_expense_voucher/          S20
│   ├── vecrm_expense_line/             S20
│   ├── vecrm_travel_voucher/           S20
│   ├── vecrm_visit_line/               S20
│   └── vecrm_voucher_audit_log/        S20
├── vecrm/patches/
│   ├── v1_1/                           S20-S26 patches (8 forward + 8 rollback)
│   └── v1_2/                           S27 patches (1 forward + 1 rollback) — NEW
└── vecrm/vecrm/voucher_counter.py      VECRM-L8 canonical
```

---

## §4 — Schema dependency map

### tabVECRM Employee (S20)

Used by: VECRM Lead, VECRM Inquiry, VECRM Assignment Ledger Entry, VECRM Expense Voucher, VECRM Travel Voucher, **VECRM Auth Reset Token (NEW S27)**

Key fields: `phone` (PK via Link autoname), `name_field` (display), `linked_user` (Link to tabUser), `reporting_approver` (Link to VECRM Employee), `failed_password_attempts`, `password_locked_until`, `failed_pin_attempts`, `pin_locked_until`, `password_hash`, `pin_hash`

### tabVECRM Auth Audit Log (S26)

Used by: vecrm.api login/logout flows, **S28 reset flow**

Event vocabulary (post-S27):
- Login: `auth.login.success`, `auth.login.fail`, `auth.login.locked` (S26)
- Logout: `auth.logout` with `path={password,pin,NULL}` (S26+S27)
- Reset (new vocabulary, will emit in S28): `auth.reset.requested`, `auth.reset.consumed`, `auth.reset.expired`, `auth.reset.invalid_token`, `auth.reset.rate_limited`

### tabVECRM Auth Reset Token (S27 NEW)

Used by: S28 reset flow backend API methods

Key fields: `token_hash` (sha256, unique), `employee` (Link), `reset_for` (Select: password|pin), `expires_at`, `consumed_at`, `ip_address`

Permissions: System Manager only. Portal users access via API methods.

### tabVECRM Lead (S20)

S27 PR #20 added: `creating_employee` (Link to VECRM Employee, nullable, populated by `create_lead` API from session.data)

13 rows backfilled to `+91-9327547536` (Ajay) per operator decision. Per-rep scoping logic deferred to PD-S28-LEAD-SCOPING-CUTOVER.

### tabVECRM Voucher Counter (S15)

Allocator. Increment column: `last_value`. NEVER NULL. Lookup pattern: `series_code = "<prefix>-<fiscal_year>"`.

Current state:
- EV-26-27=12 (Expense Voucher)
- INQ-26-27=12 (Inquiry)
- LEAD-26-27=14 (Lead)
- TV-26-27=94 (Travel Voucher, previous year)
- TV-27-28=14 (Travel Voucher, current year; origin investigation PD-S25-COUNTER-ORIGIN-S26F)

---

## §5 — Build / deploy dependencies

| Dependency | Lives at | Purpose |
|---|---|---|
| `vecrm` git repo on Mac | `~/Documents/GitHub/vecrm` | Authoring source |
| `vecrm` git repo origin | github.com/VinayEnterprises/Vinay-CRM-vecrm-app | Canonical source of truth |
| Vendored vecrm on VPS | `/opt/vecrm/vecrm-src/` | Build input (rsync'd from Mac main) |
| Containerfile | `/opt/vecrm/images/custom/Containerfile` | Build definition (NOT in any tracked repo — PD-S28-CONTAINERFILE-TRACKED) |
| apps.json secret | `/opt/vecrm/apps.json` | BuildKit secret for apps definition |
| vecrm-portal on Vercel | `https://app.vinayenterprises.co.in` | Auto-deploy on push to main |
| Frappe site | `crm.vinayenterprises.co.in` running on Contabo VPS | Backend |
| MariaDB volume | Docker named volume on VPS | Schema + data persistence |

---

## §6 — External integrations

| Service | Used by | Auth | Config |
|---|---|---|---|
| Azure AD (vemio-email-sender app reg) | [S28] vecrm-portal Graph email send | Client-credentials OAuth | `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` (Vercel env vars); reused from Vemio |
| Microsoft Graph (sendMail) | [S28] vecrm-portal reset flow | Bearer token from above | `GRAPH_SENDER_NOREPLY_VECRM = DoNotReply@vinayenterprises.co.in` (new) |
| M365 Outlook (mailbox) | [S28] receives reset emails | M365 tenant ownership | `vinayenterprises.co.in` domain with SPF/DKIM/DMARC verified |

No external integrations changed during S27. The Graph integration is teed up for S28 PD-S28-AUTH-RESET-EMAIL-MECHANISM.

---

## §7 — Docs structure (at S27 close)

```
docs/
├── architectural-locks/                   27 lock files at S27 close
│   ├── VECRM-L8.md ... VECRM-L27.md       (the lock numbers)
│   └── VECRM-LOCK-<name>.md               (the named locks)
├── dispatches/                            Per-PD dispatch + findings
│   ├── PD-S26-AUTH-PHONE-PIN-*.md
│   ├── PD-S28-AUTH-RESET-INFRA-recon-*.md
│   ├── PD-S28-AUTH-RESET-SCHEMA-dispatch.md (S27 archive)
│   ├── PD-S28-AUTH-RESET-BACKEND-API-dispatch.md (NEW, S28-ready)
│   ├── PD-S28-AUTH-RESET-EMAIL-MECHANISM-dispatch.md (NEW)
│   ├── PD-S28-AUTH-RESET-PORTAL-BFF-dispatch.md (NEW)
│   ├── PD-S28-AUTH-RESET-PORTAL-UI-dispatch.md (NEW)
│   ├── PD-S28-AUTH-RESET-EMAIL-TEMPLATE-dispatch.md (NEW)
│   └── PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE-dispatch.md (NEW)
├── handovers/                             Per-session close artifacts
│   ├── PD-S26-CLOSE-HANDOVER.md
│   ├── PD-S27-CLOSE-HANDOVER.md (NEW)
│   ├── VECRM-PENDENCY-S26-CLOSE.md
│   ├── VECRM-PENDENCY-S27-CLOSE.md (NEW)
│   ├── VECRM-DEPENDENCY-S26-CLOSE.md
│   ├── VECRM-DEPENDENCY-S27-CLOSE.md (NEW, this doc)
│   ├── S27-OPENER-PROMPT.md
│   └── S28-OPENER-PROMPT.md (NEW)
├── operating-patterns/                    Reusable patterns
│   ├── cold-check-template.md
│   └── mariadb-probe.md
├── runbooks/
│   ├── PD-S27-DEPLOY-RUNBOOK.md (NEW)
│   └── rebuild/                           First-time site bootstrap
├── session-handovers/                     S23-S25 historical handovers
└── session-scripts/                       S20 cold-check scripts (historical)
```

---

## §8 — Cross-references

- Close handover: `docs/handovers/PD-S27-CLOSE-HANDOVER.md`
- Pendency: `docs/handovers/VECRM-PENDENCY-S27-CLOSE.md`
- Deploy runbook: `docs/runbooks/PD-S27-DEPLOY-RUNBOOK.md`
- S28 opener: `docs/handovers/S28-OPENER-PROMPT.md`

**End of dependency map.**
