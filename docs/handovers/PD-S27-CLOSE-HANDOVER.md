# PD-S27-CLOSE-HANDOVER

**Session:** S27 (VECRM)
**Status:** CLOSED — 2026-05-24
**Operator:** Ajay Salvi
**Dispatcher:** Claude (chat)
**Executor:** Claude Code (IDE)

**Predecessor:** S26 close (`PD-S26-CLOSE-HANDOVER.md`, commit `f9f6229`)
**Successor:** S28 opener (`S28-OPENER-PROMPT.md`, authored as part of this close commit)

---

## §1 — One-line summary

S27 shipped 3 production PRs + closed the deploy-mechanism debt (PD-S26-DOCS-DRIFT) + landed the schema substrate for the auth-reset flow that ships in S28. All planned work plus stretch. No incidents, no rollbacks.

---

## §2 — Narrative

### §2.1 — Session opening

S27 opened from S26's clean baseline. S26-OPENER-PROMPT defined the cold-check (8 gates, all passed), and surfaced 3 work items: (1) PD-S26-AUTH-LOGOUT-PATH-RECORD (the `path` discriminator on logout audit rows), (2) the PD-S27-LEAD-SCOPING-CUTOVER schema foundation, (3) login UA polish (labels + icons + Forgot placeholder).

Cold-check at Probe 5.1 surfaced an unexpected finding: the auth principal is a SHARED user (`vecrm-portal@vinayenterprises.co.in`), not per-rep accounts. Per-rep identity lives in `VECRM Employee` keyed by phone. This was previously documented but never formally locked. Drafted as **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** for promotion at close.

### §2.2 — Primary work (3 PRs)

**PR #19 — `vecrm` — Logout audit `path` discriminator**
- `vecrm.api.vecrm_logout` now populates `path` from `frappe.session.data["vecrm_login_path"]` set during login
- Closes PD-S26-AUTH-LOGOUT-PATH-RECORD
- Squash-merge: `4f1d4a3`

**PR #20 — `vecrm` — `creating_employee` column on VECRM Lead**
- New Link→VECRM Employee column on VECRM Lead
- `create_lead` API populates from `session.data["vecrm_employee_phone"]`
- Migration patch backfilled 13 existing leads to Ajay (`+91-9327547536`) per operator decision (these were demo/admin-created, not rep-attributed)
- Paired rollback per VECRM-L22
- Squash-merge: `5cd656e`

**PR #10 — `vecrm-portal` — Login UA polish**
- Tab labels "Email" / "Phone" (replacing verbose "Email + Password" / "Phone + PIN")
- Lucide Mail / Smartphone icons
- Mode-aware "Forgot your password?" / "Forgot your PIN?" link (placeholder: "Coming soon, contact administrator")
- Wordmark + branding refresh ("Vinay Enterprises CRM")
- Squash-merge: `8540794` on vecrm-portal main

All three shipped via the verified deploy procedure that emerged through troubleshooting: vendor refresh → Containerfile sha-update (if needed) → docker build --no-cache → recreate backend → bench migrate. New image `ae202a2ef14b` ran production after primary work.

### §2.3 — Deploy mechanism reconstruction (closes PD-S26-DOCS-DRIFT)

PR #19 deploy initially failed at `VECRM_POSTINSTALL_GATE` due to a stale Containerfile sha. Investigation revealed:
- The Containerfile lives ONLY on the VPS at `/opt/vecrm/images/custom/Containerfile`, NOT in any tracked repo
- The PR #4 runbook described a Mac-buildx workflow that has never actually been used; real builds run on the VPS via `docker build` from `/opt/vecrm/`
- The Containerfile has a hardcoded sha-gate for `voucher_counter.py` that must be updated when the canonical sha changes (it had been stale since S15)

Procedure reconstructed via past-session search (`conversation_search` for S15-S22 era), Containerfile edited in place via `sed`, S15-era backups preserved alongside new S27 backups. All three primary PRs deployed cleanly through the reconstructed procedure.

**Result:** PD-S27-DEPLOY-RUNBOOK now exists as the canonical runbook. PD-S26-DOCS-DRIFT is permanently closed.

### §2.4 — Stretch work — Auth reset infrastructure

Recon (PD-S28-AUTH-RESET-INFRA) executed in parallel by Claude Code while operator handled deploy mechanics. Findings:

- **R3 (load-bearing):** Frappe v16 has NO native Microsoft 365 / Graph service type in Email Account. SMTP-only. The "configure Email Account in desk UI" path doesn't exist.
- **R5:** DMARC p=reject + strict alignment on `vinayenterprises.co.in` means email send must terminate at M365 (third-party relays would fail DMARC).
- **R1 (filled by dispatcher):** Vemio's `vemio-email-sender` Azure AD app reg has `Mail.Send` Application permission, single-tenant, REUSABLE for VECRM. Same `GRAPH_TENANT_ID`/`GRAPH_CLIENT_ID`/`GRAPH_CLIENT_SECRET` env vars work. M365 mailbox `DoNotReply@vinayenterprises.co.in` exists.

**Architectural decision (C3 final):** Mirror Vemio's portal-side Graph email pattern into `vecrm-portal/lib/email.js`. The portal owns email send + token generation; Frappe owns token storage + credential write + audit log. Frappe stays SMTP-free.

**Banked as VECRM-LOCK-VEMIO-EMAIL-PATTERN** (draft → permanent at close).

### §2.5 — Stretch work — Schema substrate (PR #21)

PD-S28-AUTH-RESET-SCHEMA shipped as the final S27 production change:

**PR #21 — `vecrm` — `VECRM Auth Reset Token` doctype**
- Single doctype with `reset_for` discriminator (password/pin)
- Fields: `token_hash` (unique, sha256), `employee`, `reset_for`, `expires_at`, `consumed_at`, `ip_address`
- Permissions: System Manager only (API methods will mediate portal access in S28)
- Audit-log event vocabulary extended (5 new events, no schema change to audit doctype)
- Paired rollback per VECRM-L22
- Squash-merge: `6d46b0d`

Deploy completed in 7 minutes wall-clock — fastest of the four S27 deploys (vendor mostly in place, no Containerfile edit needed). New image `a05637cd2be5` running production. All three post-deploy smokes passed: schema correct, insert/read/cleanup round-trip clean, unique constraint enforced via `UniqueValidationError`.

### §2.6 — Session close

Six S28 dispatches authored in this close commit:
- PD-S28-AUTH-RESET-BACKEND-API
- PD-S28-AUTH-RESET-EMAIL-MECHANISM
- PD-S28-AUTH-RESET-PORTAL-BFF
- PD-S28-AUTH-RESET-PORTAL-UI
- PD-S28-AUTH-RESET-EMAIL-TEMPLATE
- PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE

S28 opener can be authored from clean state. Six dispatches give Claude Code immediate per-sub-PD execution capability with zero recon overhead at S28 open.

---

## §3 — Final production state

| Property | Value |
|---|---|
| vecrm `main` HEAD | `6d46b0d` (PR #21 squash) |
| vecrm-portal `main` HEAD | `8540794` (PR #10 squash) |
| Production image | `vecrm-custom:latest` = `a05637cd2be5` |
| Production container uptime | recreated 2026-05-24 ~11:30 IST, healthy |
| Frappe v16 site | `crm.vinayenterprises.co.in` — HTTP 200, fully migrated |
| Next.js portal | `app.vinayenterprises.co.in` — Vercel deployed (PR #10 last night) |
| Container image audit trail (rollback tags) | s19-mac-build → s20-pre-fix-rollback → s21-pre-s22-rollback → s22-pre-build → s26-pre-s27-rollback → **s27-pre-pr21-rollback (current rollback)** → latest |
| Counter state | TV-27-28=14 (carryover from S26 close), LEAD-26-27=14 (post-Smoke-3 fix-back-to-13 + Checkpoint-C +1), INQ-26-27=12, EV-26-27=12 |
| Fleet | 36 containers (vemio + vecrm + frappe-helpdesk); zero alarm counters; AIA + Vinay HQ live tenants on vemio side |
| Production data | 13 leads (all attributed to Ajay post-backfill), 0 reset tokens (new doctype is clean) |

---

## §4 — Pendency closures (this session)

- ✅ **PD-S26-AUTH-LOGOUT-PATH-RECORD** — PR #19 ships logout `path` discriminator
- ✅ **PD-S26-DOCS-DRIFT** — PR #4 fictional runbook superseded by PD-S27-DEPLOY-RUNBOOK with §12 worked example from PR #21 deploy
- ✅ **PD-S27-LEAD-SCOPING-CUTOVER (schema half)** — PR #20 ships `creating_employee` column + backfill; per-rep scoping logic deferred to PD-S28-LEAD-SCOPING-CUTOVER (S28+)
- ✅ **PD-S28-AUTH-RESET-INFRA** — recon findings + addendum committed; C3 architecture decision locked
- ✅ **PD-S28-AUTH-RESET-SCHEMA** — PR #21 ships substrate

---

## §5 — Observations banked (S27)

22 observations surfaced during S27. Distribution:
- **Closed via PR or doc this session:** A, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U (17)
- **Closed via this close handover:** V (executor lacking conversation_search), W (Vemio email pattern duplication)
- **Banked for S28+:** B (login_path response shape — covered by S28 reset flow), C (macOS resource-fork artifact — operational hygiene), D (cold-check Gate 5 model gap — opener template improvement), E (schema column name drift — already mitigated), X (Containerfile gate stale "6 controllers" text — PD-S28-CONTAINERFILE-TRACKED), Y (patch docstring print — informational), Z (Frappe v16 metadata columns — documentation), AA (Frappe Data field min-length 64 — investigate at API author time)

See §8 of `VECRM-PENDENCY-S27-CLOSE.md` for full OBS catalog detail.

---

## §6 — Architectural locks promoted at S27 close

Three new permanent locks:

### VECRM-LOCK-PORTAL-SHARED-PRINCIPAL (promoted draft → permanent)

VECRM portal users authenticate as a single shared Frappe User (`vecrm-portal@vinayenterprises.co.in`). Per-rep identity is in `VECRM Employee` keyed by phone (E.164 `+91-XXXXXXXXXX`). Backend API methods reading `frappe.session.user` get the shared principal; per-rep identity lookups go via `frappe.session.data["vecrm_employee_phone"]`.

**Why permanent:** This is the trust model the entire portal auth surface is built on. Any change to this requires invalidating S25-S27's auth code AND PD-S28-AUTH-RESET-FLOW.

### VECRM-LOCK-VPS-PATH-CONVENTIONS (new permanent)

- `/opt/vecrm/` — frappe_docker upstream clone (the build context; NOT the vecrm app source)
- `/opt/vecrm/vecrm-src/` — vendored vecrm app source (rsync target from Mac; the `.git` directory is excluded)
- `/opt/vecrm/images/custom/Containerfile` — the build definition (NOT under version control; backed up before edits)
- `/opt/vecrm/.s<N>_pr<M>_build_<timestamp>.log` — per-deploy build logs

**Why permanent:** S27 spent 30 minutes recovering from path confusion ("which directory is the source-of-truth?"). Locking the names prevents recurrence.

### VECRM-LOCK-CONTAINERFILE-SHA-MAINTENANCE (new permanent)

When `voucher_counter.py` canonical sha changes (per VECRM-L8), the Containerfile sha-gate at line 180 must be updated in the SAME deploy. Procedure: §4 of PD-S27-DEPLOY-RUNBOOK.

Until PD-S28-CONTAINERFILE-TRACKED ships, this is a manual sed-update step. After that, the Containerfile will be in a tracked repo with a paired pin file that requires updating both in lockstep.

**Why permanent:** Stale sha = build failure. Cost: ~30 min per occurrence. Locking the procedure prevents repeated incidents.

### VECRM-LOCK-VEMIO-EMAIL-PATTERN (new permanent)

VECRM portal email-send mechanism mirrors Vemio's portal-side Graph fetch pattern (`vemio-dashboard/lib/email.js`). Same `vemio-email-sender` Azure AD app registration, same `GRAPH_TENANT_ID`/`GRAPH_CLIENT_ID`/`GRAPH_CLIENT_SECRET` env vars. Frappe v16 SMTP-only Email Account is NOT used for VECRM email; Frappe stays SMTP-free.

**Why permanent:** Establishes the canonical reset-flow architecture (portal owns email; Frappe owns token storage + credential write). Diverging from this would invalidate the entire PD-S28-AUTH-RESET-FLOW design.

---

## §7 — Effort

| Phase | Effort | Notes |
|---|---|---|
| Cold-check (8 gates) | ~45 min | Run yesterday before primary work |
| PR #19 author + smoke | ~1 hr | Yesterday |
| PR #20 author + smoke + backfill | ~1.5 hrs | Yesterday |
| PR #10 author + smoke | ~45 min | Yesterday |
| Deploy mechanism reconstruction + deploy of PR #19/20 | ~2.5 hrs | Yesterday (the big surprise) |
| Recon C1 (PD-S28-AUTH-RESET-INFRA) | ~1.5 hrs | Today; executor + dispatcher R1 fill |
| Schema PR #21 author + deploy + smoke | ~1.5 hrs | Today |
| S28 dispatches (6) | ~1.5 hrs | Today |
| Close docs (this + pendency + dependency + runbook) | ~1.5 hrs | Today |
| **Total** | **~12 hrs** | Across 2 calendar days |

S27 is the longest session of the project by ~3 hours. Half of that is the deploy mechanism reconstruction (PD-S26-DOCS-DRIFT closure) which is one-time cost — future sessions inherit the runbook.

---

## §8 — Risk register (active at S27 close)

| Risk | Severity | Mitigation status |
|---|---|---|
| Test PINs not rotated before real customer onboarding | P1 | Banked as PD-S27-TEST-PIN-ROTATION (15 min, must happen before any real production user) |
| Containerfile not in tracked repo | P1 | Banked as PD-S28-CONTAINERFILE-TRACKED (1.5 hrs) |
| Per-rep scoping not yet active on Lead list/detail BFFs | P1 | Banked as PD-S28-LEAD-SCOPING-CUTOVER (~4.5 hrs); `creating_employee` substrate ready, just needs API + BFF wiring |
| Auth reset flow not yet user-visible | P1 | Banked as PD-S28-AUTH-RESET-FLOW with 6 sub-PDs (~9-11 hrs); schema substrate live |
| Counter origin investigation (TV-27-28) | P3 | Banked as PD-S25-COUNTER-ORIGIN-S26F (30 min); no functional impact |

No P0 risks. No data integrity concerns. No security issues outstanding.

---

## §9 — Next session opener

S28 opener prompt authored as `docs/handovers/S28-OPENER-PROMPT.md` (in this same close commit). Recommended S28 scope:

**S28 Phase A (recon):** Skip — held-in-reserve recon (PD-S28-AUTH-RESET-INFRA findings) is complete.

**S28 Phase B (build), recommended order:**
1. PD-S28-AUTH-RESET-BACKEND-API + PD-S28-AUTH-RESET-EMAIL-MECHANISM (parallel; ~3 hrs)
2. PD-S28-AUTH-RESET-EMAIL-TEMPLATE (45 min)
3. PD-S28-AUTH-RESET-PORTAL-BFF (~2 hrs, depends on 1-2)
4. PD-S28-AUTH-RESET-PORTAL-UI (~2-2.5 hrs, depends on 3)
5. PD-S28-AUTH-RESET-SECURITY-REVIEW-SMOKE (~3.5-4 hrs, depends on all)

Total S28: 9-11 hours. Possibly splits into S28 (sub-PDs 1-4) + S29 (review + smoke + close). Operator decides at S28 open based on energy + calendar.

---

**S27 OFFICIALLY CLOSED.**

vecrm `main` HEAD: `6d46b0d` (will advance to S27 docs commit after this close).
Production is stable. Operator may sleep, eat, log off; production won't degrade.
