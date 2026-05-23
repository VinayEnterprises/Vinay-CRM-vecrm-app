# VECRM Pendency Document — S26 Close

**Scope:** VECRM project only (vecrm + vecrm-portal repos)
**Updated:** 2026-05-23 (S26 close)
**Format:** Open PDs grouped by priority and topic area

---

## Notes on this document

This pendency document is the canonical list of open work items in the VECRM project. It is regenerated at every session close. PDs are tagged with:

- **Origin session**: which session surfaced the item
- **Priority**: P1 (next session), P2 (within 2 sessions), P3 (background)
- **Effort estimate**: rough wall-clock
- **Status**: OPEN, IN PROGRESS, BLOCKED, DEFERRED

PDs that close during a session are moved to the relevant session's close handover, NOT removed silently.

---

## §1 — P1 (next session priority — S27)

### PD-S27-VECRM-PORTAL-BUILD-FRONTIER

**Origin:** Carryover from S25/S26 (formerly PD-S20-PORTAL)
**Effort:** Multi-session (estimated 3-5 sessions)
**Status:** OPEN — auth surface done, business surfaces remaining

The vecrm-portal Next.js application is the primary unbuilt surface. Auth path is complete (S25 email+pwd + S26 phone+PIN). Business pages still needed:

- Lead detail page (read view)
- Lead create form (shipped S24 but only basic shape — needs polish)
- Inquiry list + detail
- Inquiry → Lead conversion form (S20 backend `convert_lead_to_inquiry` API endpoint exists; portal trigger needed)
- Travel Voucher list + detail + create flow
- Sales Visit recording (Option B doctype shipped backend-side; portal flow needed)
- Per-km rate display + voucher calculation (Ahmedabad ₹2.5/km, Mumbai+Pune ₹3.5/km)

S27 should pick ONE surface (recommend Lead detail or Inquiry list) as the next dispatch.

### PD-S27-AUTH-LOGIN-AUTODETECT (Option U-C)

**Origin:** S26 (alternative to U-A)
**Effort:** 3-4 hours portal-side only
**Status:** DEFERRED — gather real-user feedback on U-A first

Auto-detect input format (email vs phone) and swap second field accordingly. Single field labeled "Email or Phone". On blur or after N chars, detect format and update second field's label + type. Combines U-A's transparency with single-input UX simplicity.

**Decision gate before starting:** wait for at least 2-3 weeks of real field-rep usage of U-A toggle. If toggle is clearly working, defer indefinitely. If users still confused, ship U-C.

### PD-S27-TEST-PIN-ROTATION

**Origin:** S26 (per VECRM-LOCK-API-KEY-ROTATION)
**Effort:** 15 min
**Status:** OPEN — must happen before any real customer onboarding

Test users have PINs `1234` and `5678` set in production. Before seeding real users:

1. Rotate Test Sales Rep PIN
2. Rotate Test HR Approver PIN
3. Document new dev PINs in `~/.vecrm-dev-creds.txt` (operator-local, NOT in repo)
4. Optional: bootstrap Ajay's own PIN if needed for production access

S27 should fold this into any "seed real user" workflow.

### PD-S26-DOCS-DRIFT (carryover from earlier session memory)

**Origin:** S20
**Effort:** 30 min
**Status:** OPEN

PR #4 runbooks describe a fictional Mac-buildx workflow; actual production builds run on the VPS via `docker build` from `/opt/vecrm/`. Need to update the runbook docs to match reality.

---

## §2 — P2 (within 2 sessions)

### PD-S26-AUTH-LOGOUT-PATH-RECORD

**Origin:** S26
**Effort:** 30 min
**Status:** OPEN

`auth.logout` audit rows currently record `path=None`. Should read the session's `login_path` value and emit the audit row with the correct discriminator (`"password"` | `"pin"`).

### PD-S26-FRAPPE-PERM-MECHANISM-PROBE / OBS-S26-I

**Origin:** S26
**Effort:** 1-2 hours
**Status:** OPEN

`frappe.get_doc` succeeds for shared portal user despite that user missing tabDocPerm rows. Mechanism unexplained. Need to:

1. Trace the perm-check code path in Frappe v16
2. Identify which bypass mechanism is triggering (probably role-based fallback, but unverified)
3. Document or harden as needed

Latent risk: if Frappe v16 patches this "bypass" in a future release, portal access for shared users could break unexpectedly.

### PD-S26-VECRM-EMPLOYEE-PERM-FLOOR / OBS-S26-H

**Origin:** S26
**Effort:** 1 hour
**Status:** OPEN

VECRM Employee perm floor is `[System Manager]` only. Other portal roles can read via the get_doc bypass (per PD-S26-FRAPPE-PERM-MECHANISM-PROBE) but this is fragile. Should explicitly add read permission for `Submitter` and `Approver` roles on VECRM Employee.

### PD-S26-PORTAL-VECRMSESSION-TYPE

**Origin:** S26
**Effort:** 2-3 hours
**Status:** OPEN

`getFrappeUser` currently returns `string | null` (just the employee name). Richer return type should surface `login_path`, `role`, full_name, employee_id, and any other session-derived fields useful for downstream UI. Type would be e.g.:

```typescript
type VecrmSession = {
  name: string;
  full_name: string;
  email: string;
  role: "Sales Rep" | "Approver" | "Admin";
  login_path: "password" | "pin";
};
```

Would require updates to `app/layout.tsx`, all consumers (currently AppShell only), and possibly the BFF route shape.

### PD-S25-COUNTER-ORIGIN-S26F (carryover)

**Origin:** S25 close (TV-27-28=14 row in counter table)
**Effort:** 30 min investigation
**Status:** PARTIAL — value captured at S26 close, origin still unclear

The counter row `TV-27-28` (last_value 14) was present at S26 cold-check baseline. It was NOT documented in the S25 close handover. Need to:

1. Identify when TV-27-28 first appeared (git log on counter docs, deploy history)
2. Determine whether the 14 count represents real production data or test seeding
3. Document in next handover

---

## §3 — P3 (background / lower priority)

### PD-S26-DEAD-AUTH-ME-ROUTE → CLOSED in S26 ✓

### PD-S25-CONTAINER-LOGS-DIRS / OBS-S26-D

**Origin:** S26
**Effort:** 1 hour
**Status:** OPEN

Container `vecrm-backend-1` is missing `/home/frappe/logs/` and `<site>/logs/` directories. Frappe writes to these for various log streams; absent dirs cause silent log drops. Need to:

1. Add directory creation to container build
2. Possibly add log volume mount to docker-compose

### PD-S26-OPENER-DOCS-DEFECTS / OBS-S26-A

**Origin:** S26
**Effort:** 30 min
**Status:** OPEN

The S26 opener prompt had defects in Gate 4 (incorrect path) and Gate 6 (incorrect column names). The opener prompt template needs updating for S27 to fix these. Captured in §6 of this document.

### PD-S26-LOCAL-BRANCH-HOUSEKEEPING / OBS-S26-U

**Origin:** S26
**Effort:** 5 min
**Status:** OPEN

Both repos have dormant local branches post-PR-merge:
- vecrm-portal: `feat/s25-vecrm-auth-portal`
- vecrm: `feat/s25-vecrm-auth-schema`

Clean up via `git branch -d <branch>` after confirming merge on origin. Banking as background hygiene; not blocking.

### PD-S26-VECRM-L8-ALLOCATOR-RELOCATE / OBS-S26-Z

**Origin:** S26
**Effort:** 30 min
**Status:** OPEN

The path `/home/frappe/frappe-bench/apps/vecrm/vecrm/utils/voucher_allocator.py` from session memory does not exist in the current container. The allocator implementation must live elsewhere. Need to:

1. Run `docker exec vecrm-backend-1 find /home/frappe/frappe-bench/apps/vecrm -type f -name "*.py" | xargs grep -l "allocate_voucher\|next_voucher\|TravelVoucher.*next\|voucher_counter" 2>/dev/null` to locate
2. Update VECRM-L8 documentation with correct path
3. Re-compute canonical sha256 and re-bank

S27 cold-check should include this as part of L8 verification.

---

## §4 — Deferred indefinitely (out of scope but tracked)

### PD-DEFERRED-VECRM-CRM-DOCTYPE-CLASH

The Frappe v16 site has both `crm` app (Frappe's first-party CRM with Lead/Deal/Pipeline doctypes) and `vecrm` app (our custom) installed in the same namespace. The doctypes are distinguished by name (`Lead` vs `VECRM Lead`) but this is a latent source of confusion (illustrated by Probe 4 failure at S26 close where `Lead` doctype lookup hit a non-existent table). Long-term, should decide whether to:

1. Uninstall the `crm` app entirely (clean separation)
2. Use `crm`'s Lead doctype and remove `VECRM Lead`
3. Continue with both, document the distinction

This is a strategic decision, not S27 work.

### PD-DEFERRED-FRAPPE-SESSION-PERSISTENCE-OPTIMIZATION

Currently `session_obj.update(force=True)` is used per VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE. Long-term, investigate whether `force=True` can be removed without breaking session integrity. Not urgent — current pattern works.

---

## §5 — Closed during S26 (audit trail)

| PD | Origin | Closure |
|---|---|---|
| PD-S26-AUTH-PHONE-PIN | S20 planning | ✅ SHIPPED via PRs #9 + #18 |
| PD-S26-DEAD-AUTH-ME-ROUTE | S25 close | ✅ CLOSED (deleted in PR #9) |
| PD-S26-UX-TOGGLE-DISCOVERABILITY (de facto OBS-S26-S) | S26 smoke #1 | ✅ FIXED via U-A addendum |

---

## §6 — S27 cold-check gates (canonical list, updated from S26 lessons)

S27 should verify these 8 gates before any work, using corrected commands from S26 lessons:

### Gate 1 — Repo + HEAD verification

```bash
cd ~/Documents/GitHub/vecrm
git checkout main && git pull origin main
git log --oneline -3
# Expected: fd69017 (HEAD) — S26 Phase 1...

cd ~/Documents/GitHub/vecrm-portal
git checkout main && git pull origin main
git log --oneline -3
# Expected: ebd3e69 (HEAD) — S26 Phase 1.B...
```

### Gate 2 — Production reachable

```bash
curl -I https://crm.vinayenterprises.co.in/
curl -I https://app.vinayenterprises.co.in/
# Both expected: HTTP 200 or 3xx redirect
```

### Gate 3 — Auth lifecycle (both paths)

```bash
# Password path:
curl -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_password \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=test.salesrep@vinayenterprises.co.in&password=testrep123"
# Expected: HTTP 200, message.login_path="password"

# PIN path:
curl -X POST https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_pin \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "phone=+91-9999900001&pin=1234"
# Expected: HTTP 200, message.login_path="pin"
```

### Gate 4 — VECRM-L8 allocator sha (NEEDS RE-DISCOVERY per OBS-S26-Z)

S27 must first locate the allocator file:

```bash
ssh vemio
docker exec vecrm-backend-1 find /home/frappe/frappe-bench/apps/vecrm -type f -name "*.py" \
  | xargs grep -l "allocate_voucher\|next_voucher\|voucher_counter\|TravelVoucher" 2>/dev/null
```

Then sha and re-bank into L8 documentation.

### Gate 5 — Portal-user invariant

Verify Test Sales Rep + Test HR Approver remain Website User with Submitter+Approver roles, both desk_access=0.

```bash
docker exec vecrm-backend-1 bash -c 'mysql -h <host> -u <dbname> -p<pass> <dbname> -e "SELECT name, user_type, enabled FROM \`tabUser\` WHERE name IN (\"test.salesrep@vinayenterprises.co.in\", \"test.hr@vinayenterprises.co.in\");"'
```

### Gate 6 — Counter state baseline

Probe counters fresh (corrected query):

```bash
docker exec vecrm-backend-1 bash -c 'mysql -h <host> -u <dbname> -p<pass> <dbname> -e "SELECT name, last_value FROM \`tabVECRM Voucher Counter\` ORDER BY name;"'
```

Expected (will have grown since S26 close):
- EV-26-27 ≥ 12
- INQ-26-27 ≥ 12
- LEAD-26-27 ≥ 13
- TV-26-27 ≥ 94
- TV-27-28 ≥ 14

### Gate 7 — VECRM Employee schema (4 PIN columns)

```bash
docker exec vecrm-backend-1 bash -c 'mysql -h <host> -u <dbname> -p<pass> <dbname> -e "DESCRIBE \`tabVECRM Employee\`;" | grep -i "pin\|password"'
```

Expected columns: `password_hash`, `pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `pin_rotated_at`, `failed_password_attempts`, `password_locked_until`.

### Gate 8 — Doctype perms (Lead/Inquiry/TravelVoucher across 4 portal roles)

Verify portal roles can read core doctypes:

```bash
docker exec vecrm-backend-1 bash -c 'mysql -h <host> -u <dbname> -p<pass> <dbname> -e "SELECT parent, role FROM \`tabDocPerm\` WHERE parent IN (\"VECRM Lead\", \"VECRM Inquiry\", \"VECRM Travel Voucher\") AND \`read\`=1 ORDER BY parent, role;"'
```

Note: per OBS-S26-I, some portal users may have functional read access despite missing tabDocPerm rows. This gate confirms the documented permission state but doesn't fully characterize the working state.

---

## §7 — Counter values at S26 close (canonical baseline)

For reference; S27 cold-check should re-probe.

```
EV-26-27   12
INQ-26-27  12
LEAD-26-27 13
TV-26-27   94
TV-27-28   14
```

Fiscal year 26-27 is the active FY in counter namespace. TV-27-28 row exists but origin is unclear (PD-S25-COUNTER-ORIGIN-S26F).

---

**End of pendency document.**

This document supersedes all prior pendency docs in the VECRM project. Next regeneration at S27 close.
