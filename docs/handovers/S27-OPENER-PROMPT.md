# S27 Opener Prompt — VECRM Session Bootstrap

**Copy-paste this prompt at the start of S27 to bootstrap the session.**

---

## Session metadata

- **Session number:** S27
- **Project:** VECRM (Vinay Enterprises CRM)
- **Repos:** `vecrm` (backend Frappe app), `vecrm-portal` (Next.js portal)
- **Operator:** Ajay Salvi
- **Working pattern:** Dispatcher (Claude chat) → Executor (Claude Code) → Operator (Ajay)

## Inheritance from S26 close

S26 shipped phone+PIN authentication (PD-S26-AUTH-PHONE-PIN) end-to-end:
- vecrm `main` HEAD: `fd69017` (PR #18 merged)
- vecrm-portal `main` HEAD: `ebd3e69` (PR #9 merged)
- Backend `vecrm.api.login_with_pin(phone, pin)` live in production
- Portal segmented-control toggle (U-A pattern) shipping on `app.vinayenterprises.co.in`

Read these three documents before starting any work:
1. `~/Documents/GitHub/vecrm/docs/handovers/PD-S26-CLOSE-HANDOVER.md`
2. `~/Documents/GitHub/vecrm/docs/handovers/VECRM-PENDENCY-S26-CLOSE.md`
3. `~/Documents/GitHub/vecrm/docs/handovers/VECRM-DEPENDENCY-S26-CLOSE.md`

(These files should have been committed at S26 close. If not present, request them from the operator.)

## Cold-check gates (run BEFORE any S27 work)

Per VECRM session discipline. All 8 gates must PASS before any phase work begins.

### Gate 1 — Repos at expected HEAD

```bash
cd ~/Documents/GitHub/vecrm
git checkout main && git pull origin main
git log --oneline -3
# Expected top line: fd69017 ... S26 Phase 1: PD-S26-AUTH-PHONE-PIN ...

cd ~/Documents/GitHub/vecrm-portal
git checkout main && git pull origin main
git log --oneline -3
# Expected top line: ebd3e69 ... S26 Phase 1.B: PD-S26-AUTH-PHONE-PIN ...
```

If either HEAD differs, halt and reconcile before proceeding.

### Gate 2 — Production reachable

```bash
curl -sI https://crm.vinayenterprises.co.in/ | head -1
curl -sI https://app.vinayenterprises.co.in/ | head -1
# Both expected: HTTP/2 200 or 3xx redirect
```

### Gate 3 — Both auth paths functional in production

**Password path:**
```bash
curl -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_password \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=test.salesrep@vinayenterprises.co.in&password=testrep123"
# Expected: HTTP 200, message.login_path="password"
```

**PIN path:**
```bash
curl -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "phone=+91-9999900001&pin=1234"
# Expected: HTTP 200, message.login_path="pin"
```

**Note:** If test PINs have been rotated (per PD-S27-TEST-PIN-ROTATION), substitute current values.

### Gate 4 — VECRM-L8 allocator sha (REQUIRES RE-DISCOVERY)

S26 noted that `/home/frappe/frappe-bench/apps/vecrm/vecrm/utils/voucher_allocator.py` does NOT exist in current container. Locate the actual allocator file:

```bash
ssh vemio
docker exec vecrm-backend-1 find /home/frappe/frappe-bench/apps/vecrm -type f -name "*.py" \
  | xargs grep -l "allocate_voucher\|next_voucher\|voucher_counter\|TravelVoucher" 2>/dev/null
```

Note the file path(s) returned. Compute sha256:
```bash
docker exec vecrm-backend-1 sha256sum <PATH_FROM_FIND>
```

**Update VECRM-L8 documentation in this session** with correct path + canonical sha. Re-bank into locks register.

### Gate 5 — Portal-user invariant intact

```bash
docker exec vecrm-backend-1 bash -c '
DB_PASS=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_password\"])")
DB_NAME=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_name\"])")
DB_HOST=$(python -c "import json; cfg=json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\")); print(cfg.get(\"db_host\", \"db\"))")
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "SELECT name, user_type, enabled FROM \`tabUser\` WHERE name IN (\"test.salesrep@vinayenterprises.co.in\", \"test.hr@vinayenterprises.co.in\");"
'
```

Expected: both users `Website User`, `enabled=1`.

### Gate 6 — Counter state (probe fresh; expect growth from S26 baseline)

```bash
docker exec vecrm-backend-1 bash -c '
DB_PASS=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_password\"])")
DB_NAME=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_name\"])")
DB_HOST=$(python -c "import json; cfg=json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\")); print(cfg.get(\"db_host\", \"db\"))")
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "SELECT name, last_value FROM \`tabVECRM Voucher Counter\` ORDER BY name;"
'
```

S26 close baseline (all should be ≥ these values):
- EV-26-27 ≥ 12
- INQ-26-27 ≥ 12
- LEAD-26-27 ≥ 13
- TV-26-27 ≥ 94
- TV-27-28 ≥ 14

### Gate 7 — VECRM Employee schema (4 PIN columns present)

```bash
docker exec vecrm-backend-1 bash -c '
DB_PASS=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_password\"])")
DB_NAME=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_name\"])")
DB_HOST=$(python -c "import json; cfg=json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\")); print(cfg.get(\"db_host\", \"db\"))")
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "DESCRIBE \`tabVECRM Employee\`;" | grep -iE "pin|password"
'
```

Expected columns include: `pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `pin_rotated_at` (plus pre-existing `password_hash`, `failed_password_attempts`, `password_locked_until`).

### Gate 8 — Doctype perms baseline

```bash
docker exec vecrm-backend-1 bash -c '
DB_PASS=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_password\"])")
DB_NAME=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_name\"])")
DB_HOST=$(python -c "import json; cfg=json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\")); print(cfg.get(\"db_host\", \"db\"))")
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "SELECT parent, role FROM \`tabDocPerm\` WHERE parent IN (\"VECRM Lead\", \"VECRM Inquiry\", \"VECRM Travel Voucher\") AND \`read\`=1 ORDER BY parent, role;"
'
```

Note: per OBS-S26-I, some portal users may have functional read access despite missing tabDocPerm rows. This gate confirms documented permissions only.

## S27 priority backlog (from pendency document)

Pick ONE of these as the primary work for S27. DO NOT try to combine — single-frontier dispatches are more reliable.

### Option A — PD-S27-VECRM-PORTAL-BUILD-FRONTIER (recommended)

Build the next business surface in the portal. Sub-options:
- **A1: Lead detail page (read view)** — straightforward, low-risk, builds momentum
- **A2: Inquiry list + detail** — extends existing list pattern from S24
- **A3: Inquiry → Lead conversion form** — wires up the S20 `convert_lead_to_inquiry` API (or its inverse)
- **A4: Travel Voucher list + detail** — useful for field-rep workflow

Recommend **A1 or A2** for S27 momentum.

### Option B — PD-S26-AUTH-LOGOUT-PATH-RECORD

30-min cleanup: read session's `login_path` during logout and emit the audit row with correct discriminator (`"password"` | `"pin"` instead of `NULL`).

Good "first work after a big session" warmup. Could be folded in alongside Option A.

### Option C — PD-S26-FRAPPE-PERM-MECHANISM-PROBE

1-2 hour investigation: why does `frappe.get_doc` succeed for shared portal user despite missing tabDocPerm? Document the actual mechanism. Hardens VECRM against future Frappe patches.

Recommend deferring unless real production risk surfaces.

### Option D — PD-S27-TEST-PIN-ROTATION (if seeding real users)

Required before any real customer onboarding. 15-min operator-driven task.

If S27 is NOT about real-user seeding, defer.

## Banked architectural decisions from S26 (carry forward)

When designing portal surfaces in S27, these S26 decisions apply:

1. **AppShell renders conditionally on null user** — no dedicated `/login` route needed for any new auth-gated surface. Just let AppShell wrap the surface; auth gate is automatic.
2. **Mode-aware patterns** — if any new surface needs to behave differently for password-path vs PIN-path users, surface `login_path` via PD-S26-PORTAL-VECRMSESSION-TYPE first.
3. **Top-of-form segmented control is the canonical mode-switch UX** — if another surface needs mode selection (e.g., "Quick add Lead" vs "Detailed add Lead"), mirror this pattern.
4. **CSS palette uses --color-vemio-* tokens** — never invent new color tokens. Mirror `.topbar-nav-link--active` for active states.
5. **aria-pressed for toggle semantics** (not full ARIA tablist).

When designing backend APIs in S27:
1. **All API methods type-annotated** (Frappe v16 `require_type_annotated_api_methods`).
2. **Use frappe.qb or frappe.get_all over raw SQL** when possible.
3. **Lockout state per-axis** if extending auth (per S26 R6 pattern).
4. **Patch + paired rollback per VECRM-L22** for any schema change.

## Locks active at S27 open

All locks from S26 carry forward. See `VECRM-DEPENDENCY-S26-CLOSE.md` §5 (in close handover) for the full list. Key new locks:

- **VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE** — dispatcher snippets are illustrative; executor mirrors existing code shape
- **VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION** — never use heredoc with `bench console`; use mysql client or `bench execute`

## Conventions reminders

- **File delivery via `present_files`**, never multi-line paste
- **Commit messages authored as files**, applied via `git commit -F`
- **`git branch --show-current` before every commit-bearing op** (OBS-S71-A)
- **VPS destructive ops require operator authorization** (VECRM-LOCK-VPS-DESTRUCTIVE-OPS)
- **All API methods type-annotated** (Frappe v16)

## Open observations (8 total — none blocking)

- OBS-S26-A — Opener prompt defects (this opener supersedes the broken S26 opener)
- OBS-S26-D — Container missing logs/ directories
- OBS-S26-F — TV-27-28 counter origin still unclear (value captured at S26 close)
- OBS-S26-H — VECRM Employee perm floor latent fragility
- OBS-S26-I — Frappe perm mechanism for shared portal user unexplained
- OBS-S26-U — Local feature branches accumulate (housekeeping)
- OBS-S26-Z — VECRM-L8 allocator file location needs re-discovery
- (Misc closed observations from S26 are in close handover §4)

## Test credentials (DEV ONLY — handle with care)

⚠️ Rotate before any real customer onboarding.

| User | Email | Phone | Password | PIN |
|---|---|---|---|---|
| Test Sales Rep | test.salesrep@vinayenterprises.co.in | +91-9999900001 | testrep123 | 1234 |
| Test HR Approver | test.hr@vinayenterprises.co.in | +91-9999900002 | testhr1234 | 5678 |
| Ajay Salvi | ajay@vinayenterprises.co.in | +91-9327547536 | (operator-known) | not bootstrapped |

## Production environment

- **VPS:** Contabo Mumbai, `217.216.58.117` (alias `vemio`), 12GB RAM, 6 CPU cores
- **Container:** `vecrm-backend-1`, image `31383918a699` (as of S26 close)
- **Site:** `crm.vinayenterprises.co.in`
- **Portal domain:** `app.vinayenterprises.co.in` (Vercel, auto-deploy from vecrm-portal main)
- **DB namespace:** `_02c50791cf17d9de` (per-site Frappe DB)

## How to start S27

1. Operator: review this opener, confirm cold-check gates 1-8 pass
2. Operator: paste cold-check outputs to dispatcher
3. Dispatcher: adjudicate gates, identify any drift since S26 close
4. Operator: pick S27 primary work (Option A1/A2/A3/A4 or B/C/D)
5. Dispatcher: author Phase A recon dispatch for chosen work
6. Phase A recon → R-findings → Phase B A2 dispatch → A2 implementation → smoke → PR

## Estimated S27 duration

If picking Option A1 (Lead detail page): ~4-6 hours including cold-check, recon, impl, smoke, PR.
If picking Option B (logout path record): ~1-1.5 hours.
If combining A1 + B: ~5-7 hours.

---

**End of S27 opener prompt.**

When ready, paste this entire prompt to a fresh Claude session and proceed through the gates.
