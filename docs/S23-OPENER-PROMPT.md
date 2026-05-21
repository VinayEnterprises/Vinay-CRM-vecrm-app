# S23 OPENER PROMPT — VECRM Session 23

Use this prompt at the start of S23. Paste verbatim. Do NOT trust prior handover prose without cross-check.

---

## CONTEXT FOR CLAUDE

You are opening VECRM Session 23. The prior session (S22) shipped:
- vecrm-portal PR #3 (MOBILE-NAV + FAVICON polish, at `743cabb`)
- vecrm PR #9 (VECRM Travel Voucher Layer-2 keystone + allocator concurrency fix, squash-merged at `a428d2a`)

S22 also discovered and fixed a latent stale-read bug in the voucher allocator that had been present since the allocator's first commit. The bug was found via 6 falsified hypotheses + one Round 2 Claude Code recon. New architectural lock VECRM-S22-A was earned. 8 OBS-S22 candidates were raised.

S22 close handover is at: `docs/session-handovers/S22-close-handover.md` (in vecrm repo)
S22 pendency register is at: `docs/VECRM-PENDENCY-REGISTER.md` (in vecrm repo, comprehensive)

**Critical posture per OBS-S22-B:** prior handovers have drifted from ground truth. The handover prose can lie. Cross-check everything. Specifically:
- Prior handovers referenced site name `_02c50791cf17d9de` — that was wrong. Actual site is `crm.vinayenterprises.co.in`
- Prior handovers claimed Layer-2 was "complete" when only Voucher Counter was actually built; Travel Voucher + Visit Line were never written until S22

**Critical posture per OBS-S22-F:** if a bug requires more than 3 falsified hypotheses to find, escalate to Claude Code parallel-read recon. Don't keep cycling hypotheses.

**Critical posture per OBS-S22-A:** single-threaded correctness is NOT concurrent correctness. Every allocator/counter touch MUST be concurrency-tested before declared shippable.

---

## SESSION-OPEN COLD-CHECK GATES

Run these BEFORE any work. Do not skip. If any gate fails, STOP and reconcile before proceeding.

### Gate 1: Branch and remote state

```bash
cd ~/Documents/GitHub/vecrm
git branch --show-current
# Expect: main

git status
# Expect: On branch main, working tree clean (or only untracked work-in-progress)

git log --oneline -5
# Expect: top commit is the S22 handover commit OR a428d2a (PR #9 squash merge)

git pull origin main
# Expect: Already up to date
```

### Gate 2: L8 dual-surface sha verification

```bash
echo "Local sha:"
shasum -a 256 ~/Documents/GitHub/vecrm/vecrm/vecrm/voucher_counter.py

echo "Container sha:"
ssh root@217.216.58.117 'docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py'

# Both must be:
# 91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9
```

If they drift: STOP. Reconcile (probably scp + docker cp the local version onto the container). Do not touch any other code until L8 is re-gated.

### Gate 3: DB state — isolation, version, site

```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute frappe.db.sql --args "[\"SELECT @@innodb_snapshot_isolation, @@global.innodb_snapshot_isolation, @@version\"]"'

# Expect: innodb_snapshot_isolation 1 or 0 (note which), MariaDB 11.8.6
```

Document the SI state in your S23 first message. If SI is OFF and we want it ON: restart vecrm-db-1 container OR `SET GLOBAL innodb_snapshot_isolation = ON` via root.

### Gate 4: Container health

```bash
ssh root@217.216.58.117 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Expect: 9 containers Up (some may show 'unhealthy' on vecrm-freeradius — that's a known false alarm per S64+ history; benign)
```

### Gate 5: Counter state

```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.sql" --args "[\"SELECT counter_key, last_value FROM tabVECRM_Voucher_Counter\"]"'

# Or via the actual table name:
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.sql" --args "[\"SELECT counter_key, last_value FROM \\\`tabVECRM Voucher Counter\\\`\"]"'

# Expect:
# - TV-26-27 at last_value ~78
# - TV-27-28 at last_value ~14
```

### Gate 6: Pendency register cross-check

Open `docs/VECRM-PENDENCY-REGISTER.md` (the comprehensive one drafted post-S22). Spot-check 2-3 PART E component states against ground truth:

```bash
# Verify Travel Voucher doctype exists
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.exists" --args "[\"DocType\", \"VECRM Travel Voucher\"]"'

# Verify VECRM Voucher Audit Log doctype does NOT exist (per register PART E)
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.exists" --args "[\"DocType\", \"VECRM Voucher Audit Log\"]"'

# Verify phantom table still exists (per register PART G)
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.sql" --args "[\"SELECT COUNT(*) FROM \\\`tabVECRM Sales Visit\\\`\"]"'
```

If any of these contradict the register, the register is wrong — update it before any other work.

---

## SESSION OPENING SUMMARY (Claude should produce this after gates pass)

After running gates 1-6, Claude should produce a concise opening summary covering:

1. **L8 dual-surface verified** ✅ / ❌
2. **SI state on DB:** ON / OFF (capture which)
3. **All 9 containers healthy:** ✅ / ❌
4. **Counter state matches expected:** ✅ / ❌
5. **Register cross-check results:** any drift?
6. **Posture for S23 work:** ready to proceed / needs reconciliation first

---

## RECOMMENDED S23 PRIORITIES (in order)

### Priority 1 (BLOCKING PRODUCTION): PD-S22-VOUCHER-AUDIT

**Why first:** voucher workflow cannot ship to sales/HR without an audit trail. Currently audit calls are commented out in `vecrm_travel_voucher.py`. The blocking issue is that `VECRM User Audit Log` is unfit for document audit (both actor and target are Link to VECRM Employee).

**Scope:**
1. Design `VECRM Voucher Audit Log` doctype:
   - actor (Link to VECRM Employee, required)
   - target_doctype (Data)
   - target_name (Data)
   - action (Select: insert, submit, approve, cancel, amend)
   - from_state, to_state (Data, optional)
   - at_timestamp (Datetime, default now())
   - metadata_json (Long Text, optional)
2. Permission lockdown (read-only for all UI; only controller can insert via raw SQL or whitelisted method)
3. Re-enable audit calls in `vecrm_travel_voucher.py` (uncomment `_audit()` calls, adjust field names to match new doctype)
4. Re-run §5 single-thread + §6 concurrency hard-gate
5. Add §7 — concurrency test for audit table itself (10 concurrent submits = 20 audit rows = no contention expected, but verify per OBS-S22-A)
6. Commit as separate PR

**Estimated:** 2-3 hours

### Priority 2 (Layer-2 completion): PD-S22-EXPENSE-VOUCHER

**Why second:** completes Layer-2 (Phase 3). MUST land AFTER VOUCHER-AUDIT so audit shape is established.

**Scope:** Build `VECRM Expense Voucher` following Travel Voucher pattern. Per-line category (Select: Hotel/Food/Supplies/Communication/Misc), amount, description, attachment. Series `EV` (separate counter). Apply VECRM-S22-A from start. §6 hard-gate required.

**Estimated:** 4-6 hours

### Priority 3 (low-energy fallback): PD-S22-LOADING-FLASH

**Why:** discrete, contained, banked dispatch ready. Use if energy is lower OR if waiting on something else.

**Scope:** Path δ SSR cookie hydration in vecrm-portal. Banked dispatch at `/mnt/user-data/outputs/DISPATCH-S22-AUTH-SSR-HYDRATION.md`.

**Estimated:** 1-2 hours

---

## EXPLICIT ANTI-DRIFT GUARDS

Per OBS-S22-* patterns from prior session, S23 MUST observe:

### Anti-drift 1: Cross-check before code
Before writing ANY code that touches a doctype, read its JSON file (or `frappe.get_meta`) for the actual field list. Six recon failures in S22 cost ~3 hours total. Per OBS-S22-C.

### Anti-drift 2: Concurrency-test every allocator touch
Any change that touches `voucher_counter.py`, any new voucher doctype, any new code that allocates from a counter — MUST be exercised under 10-thread concurrency before declaring shippable. Per OBS-S22-A + VECRM-S22-A.

### Anti-drift 3: Escalate after 3 falsified hypotheses
If diagnosing a bug and 3 hypotheses are falsified by data, STOP dispatcher-mode hypothesizing and escalate to Claude Code parallel-read recon. Per OBS-S22-F.

### Anti-drift 4: Mirror code path in diagnostics
When writing a diagnostic for a suspected bug, mirror the production code path's SQL/transaction shape EXACTLY. Approximations test approximations, not the bug. Per OBS-S22-G.

### Anti-drift 5: Use artifact-flow for diagnostics > 20 lines
Don't heredoc-via-SSH-via-docker. Pattern: write diagnostic as artifact → operator downloads to ~/Downloads → scp → docker cp → bench execute. Per OBS-S22-D.

### Anti-drift 6: Operator endurance is a structural signal, not a heroism metric
If 3+ falsified hypotheses pile up, that's a signal to stop and reconcile, independent of operator energy. Per OBS-S22-H.

---

## WHAT TO READ BEFORE STARTING S23 WORK

In order:
1. **This opener prompt** (you're reading it)
2. **`docs/session-handovers/S22-close-handover.md`** — context for what shipped + what was learned
3. **`docs/VECRM-PENDENCY-REGISTER.md`** — comprehensive tactical + strategic backlog
4. **`docs/architectural-locks/VECRM-S22-A.md`** — the new lock from S22
5. **`docs/architectural-locks/VECRM-L8.md`** — verify banked sha matches what's in production

After reading: run cold-check gates 1-6, produce opening summary, then propose S23 work plan.

---

## CONTEXT THAT IS NEVER ALLOWED TO DRIFT

These are facts that have caused confusion before. Lock them in:

- **Site name:** `crm.vinayenterprises.co.in` (NOT `_02c50791cf17d9de`)
- **VPS:** Contabo Mumbai `217.216.58.117`
- **MariaDB version:** 11.8.6
- **Default DB isolation:** REPEATABLE-READ
- **innodb_snapshot_isolation default in 11.8.6:** ON
- **Allocator canonical sha (post-S22):** `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`
- **Layer-2 status:** 75% complete (Voucher Counter ✅, Travel Voucher ✅, Visit Line ✅, Expense Voucher ❌)
- **Test employees:** `+91-9999900001` (Sales Rep), `+91-9999900002` (HR)
- **Counter state at S22 close:** TV-26-27 at 78, TV-27-28 at 14

---

*Use this prompt verbatim at S23 open. Operator may add ad-hoc context after the structured section, but do not skip the cold-check gates.*
