# S26 — Opening Prompt

**Use this prompt verbatim as the first message of a new chat to start Session 26 of VECRM.**

---

I am continuing VECRM development. This is Session 26 (S26). Please read this entire prompt before proposing any work plan, then run the cold-check gates below.

---

## 1. Who I am and what we're building

I'm Ajay Salvi, solo founder of Vinay Enterprises. We have two products:

- **VEMIO** — managed network monitoring SaaS for MSPs (separate stack, separate work track)
- **VECRM** — our internal CRM + sales-tooling product. THIS is what S26 works on.

VECRM is a Frappe v16.18.2 app on Contabo Mumbai (`crm.vinayenterprises.co.in`, IP `217.216.58.117`) with a Next.js 16 portal hosted on Vercel (`vecrm-portal`). Two repos:

- `VinayEnterprises/Vinay-CRM-vecrm-app` (the Frappe app)
- `VinayEnterprises/vecrm-portal` (the Next.js portal)

I am the only developer. I use Claude (you) as the architectural and planning partner; Claude Code as the implementation executor. I make decisions; you adjudicate diffs and architectural calls; Claude Code edits files, runs commands, and ferries artifacts.

---

## 2. What S25 just shipped (you must know this)

S25 closed Saturday May 23, 2026 IST ~01:00 with **PD-S25-VECRM-AUTH v2** shipped end-to-end:

- Email+password authentication for VECRM Portal
- 7 commits in vecrm (squash-merged as `5e0df3b` via PR #16)
- 1 commit in vecrm-portal (squash-merged as `8165f7a` via PR #8, Vercel auto-deployed)
- Three identity types log in: Test Sales Rep, Test HR Approver, Ajay (Admin)
- Account lockout (5 attempts → 15 min), audit log emission, session persistence verified across HTTP boundary
- VECRM Lead + VECRM Inquiry doctype perms extended for portal roles (Phase 5.5 fix)

**5 new architectural locks earned in S25:**
- VECRM-LOCK-FRAPPE-SESSION-PERSISTENCE
- VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE
- VECRM-LOCK-PORTAL-USER-ROLES
- VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE
- VECRM-LOCK-FILE-DELIVERY-NOT-PASTE

**47 OBS observations filed in S25 (catalog A-AX).** Notable failure patterns to NOT repeat:

- **OBS-S25-AM/AN/AO/AP** — dispatcher cross-turn state-tracking failures on source artifacts. Fix: source artifacts > 30 lines via `present_files` ONLY, never inline chat paste.
- **OBS-S25-AV** — §risk sections need verification gates at the moment the risk becomes structurally concrete, not just acknowledgment.
- **OBS-S25-AS** — before flagging a blocker, run `git log --oneline -5` to confirm it isn't already-resolved-and-deployed.

---

## 3. Reading order (do this BEFORE proposing any work plan)

In this order, in the vecrm repo:

1. **`docs/session-handovers/S25-close-handover.md`** — primary input, full session record
2. **`docs/VECRM-PENDENCY-REGISTER.md`** — comprehensive tactical + strategic backlog (regenerated at S25 close)
3. **`docs/VECRM-DEPENDENCY-MAP.md`** — infrastructure state, versions, what depends on what (updated at S25 close)
4. **`docs/architectural-locks/`** — formal locks, one file each. **Read all 5 new S25 lock files** (FRAPPE-SESSION-PERSISTENCE, PASSWORD-FIELDTYPE-AVOIDANCE, PORTAL-USER-ROLES, RISK-NEEDS-VERIFICATION-GATE, FILE-DELIVERY-NOT-PASTE) plus VECRM-S22-A (allocator), VECRM-LOCK-VPS-DESTRUCTIVE-OPS, VECRM-LOCK-NEXTJS-NAME-PARAM-DECODE.

---

## 4. Cold-check gates (RUN BEFORE ANY CODE)

Per OBS-S22-B (do not trust prose; verify against ground truth at session-open), execute these gates and report results before proposing work.

### Gate 1 — Repos and HEADs

```bash
cd ~/Documents/GitHub/vecrm
git checkout main
git pull origin main
git log --oneline -5
# expect: top commit is S25 docs PR (or 5e0df3b if S25 docs PR hadn't merged yet); HEAD on main

cd ~/Documents/GitHub/vecrm-portal
git checkout main
git pull origin main
git log --oneline -5
# expect: top commit is 8165f7a (S25 PR #8 squash)
```

### Gate 2 — Production reachability

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://crm.vinayenterprises.co.in/api/method/ping
# expect: 200 (or 401/403, which still means Frappe is up)
```

### Gate 3 — Auth smoke against production

```bash
COOKIE_FILE=/tmp/vecrm-s26-coldcheck.txt
rm -f "$COOKIE_FILE"

curl -sS -c "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.login_with_password \
  -H "Content-Type: application/json" \
  -d '{"email": "test.salesrep@vinayenterprises.co.in", "password": "testrep123"}' \
  -w "\nHTTP_STATUS=%{http_code}\n"

curl -sS -b "$COOKIE_FILE" \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.get_session_employee \
  -w "\nHTTP_STATUS=%{http_code}\n"

curl -sS -b "$COOKIE_FILE" -X POST \
  https://crm.vinayenterprises.co.in/api/method/vecrm.api.vecrm_logout \
  -w "\nHTTP_STATUS=%{http_code}\n"

rm -f "$COOKIE_FILE"
```

**Expected:** 3 × HTTP 200. The middle call returns `"login_path":"password"` in the response. If anything other than 200, halt and diagnose before proceeding.

### Gate 4 — Allocator sha (VECRM-L8)

```bash
ssh root@217.216.58.117 'docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/utils/voucher_counter.py'
# expect: 91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9
```

### Gate 5 — Shared portal user state

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
user = "vecrm-portal@vinayenterprises.co.in"
print(f"user_type: {frappe.db.get_value('User', user, 'user_type')}")  # expect: Website User
print(f"roles: {sorted(frappe.get_roles(user))}")  # expect: ['All', 'Guest', 'VECRM Approver', 'VECRM Submitter']
for r in ["VECRM Submitter", "VECRM Approver"]:
    print(f"{r}.desk_access = {frappe.db.get_value('Role', r, 'desk_access')}")  # expect: 0 for both
EOF
```

### Gate 6 — Counter state

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
counters = frappe.db.sql("""
    SELECT prefix, fiscal_year, last_value
    FROM `tabVECRM Voucher Counter`
    ORDER BY prefix, fiscal_year
""", as_dict=True)
for c in counters:
    print(f"  {c}")
EOF
# expect: TV-26-27 at 94, EV-26-27 at 12, LEAD-26-27 at 13, INQ-26-27 at 12
```

### Gate 7 — VECRM Employee credential fields exist

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
meta = frappe.get_meta("VECRM Employee")
auth_fields = [f for f in meta.fields if f.fieldname in ("password_hash", "failed_password_attempts", "locked_until", "last_login_at")]
for f in auth_fields:
    print(f"  {f.fieldname}: {f.fieldtype}")
# expect:
#   password_hash: Data  (NOT Password — VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE)
#   failed_password_attempts: Int
#   locked_until: Datetime
#   last_login_at: Datetime
EOF
```

### Gate 8 — VECRM Lead and VECRM Inquiry portal-role perms

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
for dt in ["VECRM Lead", "VECRM Inquiry", "VECRM Travel Voucher"]:
    rows = frappe.db.sql("SELECT role FROM tabDocPerm WHERE parent=%(dt)s ORDER BY role", {"dt": dt}, as_dict=True)
    print(f"{dt}: {[r.role for r in rows]}")
# expect: each shows [System Manager, VECRM Admin, VECRM Approver, VECRM Submitter]
EOF
```

---

## 5. Anti-drift guards (active in S26)

Per the OBS-S25 patterns codified as locks. S26 MUST observe:

### Guard 1 — Source artifacts via file delivery, not chat paste

Per VECRM-LOCK-FILE-DELIVERY-NOT-PASTE. Any source > 30 lines goes through `present_files`. Operator downloads, moves to repo. Never reconstruct files from chat descriptions.

### Guard 2 — §risk requires §verification-gate

Per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE. Every risk section in S26 dispatches must include a concrete verification check executed at the moment the risk becomes structurally concrete.

### Guard 3 — `git log --oneline -5` before flagging a blocker

Per OBS-S25-AS. Before flagging "this is still broken" or "the source is wrong," run a git-history check to confirm the issue isn't already-resolved-and-deployed.

### Guard 4 — Verify symbols before using them

Per OBS-S25-AT (Lead vs VECRM Lead) and Phase 0.5 source-read discipline. Before writing code that depends on a Frappe internals symbol (`frappe.foo.bar`, `LoginManager.something`), verify it exists and has the expected signature via `bench console` source-read.

### Guard 5 — Use `db_update` not `.save()` for column-only updates

Per VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE and OBS-S25-AK. Even though `password_hash` is now Data fieldtype (survives `.save()`), `db_update()` is the cleaner primitive for column-only updates. Use `frappe.db.set_value()` for one-off writes.

### Guard 6 — Cross-check before code

Per OBS-S22-C (carried from S22). Before writing code that touches a doctype, read its JSON file or call `frappe.get_meta(doctype)` to confirm the actual field list. Do NOT assume field names from memory.

### Guard 7 — Branch-first commits + squash-merge with deletion

Per VECRM-L13 and OBS-S71-A. `git branch --show-current` before AND after every commit-bearing or merge-bearing bash invocation. `gh pr merge --squash --delete-branch` for all merges.

### Guard 8 — VECRM dispatch never touches VEMIO

Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS. The Mumbai VPS hosts both VECRM and VEMIO containers. VECRM work NEVER touches `vemio-*` containers, files, or DB.

---

## 6. Context that is never allowed to drift

These facts have caused confusion before. Lock them in:

- **Site name:** `crm.vinayenterprises.co.in` (NOT `_02c50791cf17d9de`)
- **VPS:** Contabo Mumbai `217.216.58.117`
- **Frappe version:** v16.18.2
- **MariaDB version:** 11.8.6
- **Default DB isolation:** REPEATABLE-READ
- **`innodb_snapshot_isolation` default in 11.8.6:** ON
- **`require_type_annotated_api_methods` in hooks.py:** TRUE (every `@frappe.whitelist()` MUST have type annotations)
- **Allocator canonical sha (VECRM-L8):** `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`
- **`vecrm` main HEAD at S25 close:** `5e0df3b` (post-PR #16, may increment with S25 docs PR)
- **`vecrm-portal` main HEAD at S25 close:** `8165f7a`
- **Counter state:** TV-26-27 at 94, EV-26-27 at 12, LEAD-26-27 at 13, INQ-26-27 at 12
- **Test employees:** Test Sales Rep `+91-9999900001` (Sales Rep), Test HR Approver `+91-9999900002` (HR), Ajay `+91-9327547536` (Admin) — all Ahmedabad
- **Shared portal user:** `vecrm-portal@vinayenterprises.co.in` — Website User + VECRM Submitter + VECRM Approver
- **Layer-2 status:** Travel Voucher ✅, Expense Voucher backend ✅ portal ❌, Approver portal ❌
- **Layer-3 status:** Lead → Inquiry pipeline ✅ (multi-user since S25)

---

## 7. Priority work options for S26

The next session frontier is **auth backlog** (highest priority) plus **portal continuation** (largest visible-progress lever). Pick one (or propose a hybrid):

### Option A — Phone+PIN backend (recommended priority 1)

**PD-S26-AUTH-PHONE-PIN.** Estimated 4-6 hours.

Add `pin_hash` (Data fieldtype), `failed_pin_attempts`, `pin_locked_until`, `last_pin_login_at` fields to VECRM Employee. New `vecrm.api.login_with_pin(phone: str, pin: str)` endpoint. Same lockout/audit/`_issue_session` mechanics as email+password. Portal additions: PIN login UI as an alternate option on `/login`.

**Why this is recommended for S26 Phase 1:**
- Direct continuation of S25's auth work — same mental model, lower risk of architectural surprise
- Field reps will use phones; PIN is faster on mobile than email+password
- Backend-only at the start, then ~1h of portal UI to expose it

### Option B — Email-based password reset flow

**PD-S26-AUTH-RESET + PD-S26-AUTH-MS-GRAPH.** Estimated combined 10-15 hours.

Requires:
1. Microsoft Graph wiring for outbound email (4-6h)
2. `VECRM Auth Reset Token` doctype + endpoints (6-10h)
3. Portal UI for reset flow (~2h)

**Why consider this:** without reset, the only way to recover a forgotten password is `admin_set_credential` via console (operator-only). For real-user rollout, reset is table-stakes.

### Option C — Expense Voucher portal (Sub-B)

**PD-S26-PORTAL-SUB-B-EXPENSE.** Estimated 10-16 hours.

A1 recon banked from S24 dispatch D. Portal screens (create / list / detail) for VECRM Expense Voucher. Backend already exists from S23 PR #12.

**Why consider this:** Sub-A (Travel Voucher) works for all 3 roles post-S25. Sub-B is the symmetric next, and the operator can submit real expense vouchers once it lands.

### Option D — Approver portal (Sub-B2)

**PD-S26-PORTAL-SUB-B2-APPROVER.** Estimated 6-10 hours.

Backend APIs (`approve_travel_voucher`, `approve_expense_voucher`) already exist. Need `/approver/queue` page + action UI. Should land AFTER Sub-B if both ship in S26.

### My recommendation

**S26 Phase 1 = Option A (Phone+PIN).** It's the smallest unit of work that ships real value (mobile-friendly auth), directly continues S25's mental model, and has the lowest risk profile.

S26 Phase 2 = Option C OR Option B depending on appetite. If operator wants real users using the portal soon: C (Expense Voucher portal). If operator wants to harden auth before user rollout: B (Reset flow).

---

## 8. Working pattern (carried, NEVER drifts)

- **Dispatcher (Claude in chat)** authors dispatch documents, source-reads, prescriptions; adjudicates diffs.
- **Executor (Claude Code in IDE)** runs commands, edits files, ferries artifacts, runs verifications.
- **Operator (Ajay)** approves dispatches, runs state-changing ops (git, SQL on production, PR merges), makes final architectural calls.

State-changing operations the operator ALWAYS runs:
- `git add`, `git commit`, `git push` (committing)
- `gh pr create`, `gh pr merge` (PR ops)
- `scp`, `docker cp`, `docker exec ... bench migrate` (VPS deploys)
- Production SQL approvals (anything `WRITE`, `DROP`, `ALTER`)
- Vercel smoke tests (browser-based)

State-changing operations Claude Code CAN run:
- File reads, file edits in the local repo working tree
- `git status`, `git diff`, `git log`, `git branch --show-current` (read-only git)
- `python -m py_compile`, JSON validation, AST checks (local verification)
- `bench console` reads (source inspection, schema introspection — read-only)

---

## 9. After cold-check gates pass

Propose a work plan for S26 in this shape:

1. Which option (A/B/C/D or hybrid) and why
2. Recon dispatch (R1-R6) if architectural unknowns exist
3. Implementation dispatch (A2) shape
4. Phase breakdown with verification gates
5. Estimated session duration

Then I'll approve or refine before any code starts.

---

## 10. One final note

S25 was a 14-hour session that surfaced 47 OBS observations. The biggest structural lessons:

1. **Source artifacts via file delivery, not chat.** (VECRM-LOCK-FILE-DELIVERY-NOT-PASTE)
2. **Risks need verification gates, not just acknowledgment.** (VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE)
3. **Frappe internals require source-reads, not memory.** (Phase 4.6/4.7 mechanism discoveries)
4. **Cross-turn state-tracking fails; mechanize what's repeatable.** (the 4 dispatcher failures and how they were resolved)

S26 doesn't have to repeat these. The locks exist; honor them.

---

**End of S26 opener prompt. Run the cold-check gates and tell me what you find.**
