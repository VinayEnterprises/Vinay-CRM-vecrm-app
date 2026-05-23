# PD-S26-AUTH-PHONE-PIN — Recon Dispatch (R1–R6)

**Session:** S26 Phase 1 recon
**Dispatcher:** Claude (chat)
**Executor:** Claude Code
**Operator:** Ajay Salvi
**Authorized:** S26 cold-check pass + operator selection of Option 1 (full recon)
**Deliverable:** R1–R6 findings report (also via `present_files`)
**Estimated wall-clock:** 30–45 min

---

## §0 — Cold-check inheritance (no rerun needed)

All 8 S26 cold-check gates passed earlier this session. Inheritance into the recon:

- vecrm@`6c39113`, vecrm-portal@`8165f7a` (both main, both up-to-date)
- Production auth lifecycle: green (login → get_session_employee `login_path:"password"` → logout)
- VECRM-L8 allocator sha: `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`
- Portal-user invariant: Website User + Submitter+Approver, both `desk_access=0`
- Counter state: TV-26-27=94, EV-26-27=12, INQ-26-27=12, LEAD-26-27=13 (+ TV-27-28=14 banked per OBS-S26-F)
- VECRM Employee credential fields: `password_hash:Data`, lockout trio present
- Doctype perms: Lead/Inquiry/TV all show 4-role roster

Recon does NOT touch production state. Read-only source-reads + read-only Frappe introspection.

---

## §1 — Scope (what this recon answers)

PD-S26-AUTH-PHONE-PIN is the **phone+PIN companion** to S25's email+password authentication. This recon banks concrete answers to six architectural questions so the A2 implementation dispatch is execution-only, not discovery.

**In scope for the recon:**
- Source-reads of `vecrm/api.py` (esp. `_issue_session`, `login_with_password`, `_on_failure`)
- Source-reads of `vecrm/utils/roles.py` (`EMPLOYEE_ROLE_TO_FRAPPE_ROLES`)
- Schema introspection of `tabVECRM Employee` (column inventory)
- Phone-format inspection of 3 production employees
- Audit-log event-name inventory
- Frappe passlibctx default verification

**Out of scope for the recon (deferred to A2 dispatch):**
- Any code or schema changes
- Any migration patches
- Any portal UI work
- Anything destructive

---

## §2 — Working pattern

**Per the established split:**
- **Dispatcher (Claude in chat):** authored this dispatch; will adjudicate findings.
- **Executor (Claude Code):** runs source-reads, introspections, ferrying. All commands listed inline below.
- **Operator (Ajay):** runs the bench-console introspections (R4/R5/R6); reviews findings; authorizes proceeding to A2 dispatch.

**Per VECRM-LOCK-VPS-DESTRUCTIVE-OPS:** zero state-changing ops in this recon. All introspections are read-only `SELECT` or `frappe.db.get_value` / `frappe.get_meta`. The recon report itself is a markdown file delivered via `present_files`.

**Per OBS-S26-E lesson (banked from earlier in S26):** introspections use single-statement bench-console queries with dict/list comprehensions, NOT for-loops in heredocs.

---

## §3 — Recon execution plan

Six recon questions. Each has:
- **Question** (what we're trying to answer)
- **Verification command** (the exact source-read or introspection)
- **Pass criteria** (what the answer needs to look like to unblock A2)
- **Fallback** (what we do if the answer is unexpected)

Recon runs in this order: **R4 → R5 → R6** (operator-run introspections, batched), **R1 → R2 → R3** (executor source-reads, batched). The reason: R4/R5/R6 are quick console queries; R1/R2/R3 require reading actual Python source from the local repo.

---

## §4 — R4: Schema introspection — VECRM Employee column inventory

**Question:** What are the actual columns on `tabVECRM Employee`? Will the four new columns (`pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `last_pin_login_at`) collide with anything existing?

**Why this matters:** The opener prompt had three column-name defects (OBS-S26-A). We don't assume schema; we verify.

**Verification command (operator runs):**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
print([c["Field"] for c in frappe.db.sql("DESCRIBE `tabVECRM Employee`", as_dict=True)])
EOF
```

**Pass criteria:**
- Output is a list of column names
- None of these four names appear: `pin_hash`, `failed_pin_attempts`, `pin_locked_until`, `last_pin_login_at`
- These four DO appear (sanity check on S25 ship): `password_hash`, `failed_password_attempts`, `locked_until`, `last_login_at`
- `name` column exists (used as the doc identifier — phone)
- `vecrm_phone` column exists (the actual phone field; `name` is set from it via `autoname=field:vecrm_phone`)
- `vecrm_email` column exists (used for email-path login)

**Fallback if columns collide:** Stop. Re-author A2 migration with renamed target columns. Unlikely — the four names are PIN-specific.

---

## §5 — R5: Phone format normalization across production employees

**Question:** What format do the 3 production phone values use? Do we need normalization in `login_with_pin(phone: str, pin: str)`?

**Why this matters:** Field reps will enter phones on a mobile keypad — possibly without the `+91-` prefix, possibly with spaces. If the API expects exact-match against the `name` column (which is `+91-9XXX...`), we need a canonical normalization step at the API boundary.

**Verification command (operator runs):**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
print(frappe.db.sql("SELECT name, vecrm_phone, vecrm_email, role, vecrm_account_status FROM `tabVECRM Employee` ORDER BY name", as_dict=True))
EOF
```

**Note (OBS-S26-G):** Earlier version of this dispatch used `WHERE status='Active'` — the actual column name is `vecrm_account_status` (per R4 schema introspection). Corrected inline. Lesson: dispatcher must run R4-style schema introspection BEFORE authoring queries that reference column names, not assume from memory.

**Pass criteria:**
- 3 rows returned (Test Sales Rep, Test HR Approver, Ajay)
- All `vecrm_account_status='Active'`
- All `name` values match the format `+91-<10 digits>` (country code, single dash, 10 digits — confirmed)
- `name` == `vecrm_phone` for all rows (autoname invariant)
- Canonical format documented in the recon report

**Banked design decision:** Format is consistent `+91-<10 digits>` (single dash after country code, no internal separators). A2 normalization helper:

```python
def _normalize_phone(phone: str) -> str:
    """Canonicalize portal-submitted phone to match VECRM Employee.name format.

    Target: '+91-' followed by exactly 10 digits.
    Accepts variants: with/without country code, with/without separators
    (spaces, dashes, parens), with/without leading 0.
    """
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10:
        return phone  # let lookup fail naturally; caller emits invalid_credentials
    return f"+91-{digits}"
```

This 14-line helper is the same shape as `login_with_password`'s email lookup (which doesn't need normalization because email is exact-match).

**Fallback if format is inconsistent:** Document each format variant, update normalization to handle all cases.

---

## §6 — R6: Audit-log event-name inventory

**Question:** What events does `tabVECRM Auth Audit Log` currently contain? Will PIN events collide or share cleanly?

**Why this matters:** The audit log is shared between password and PIN paths. We need the `event` namespace to NOT collide while still being queryable by path.

**Verification command (operator runs):**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
print(frappe.db.sql("SELECT event, path, reason, COUNT(*) AS n FROM `tabVECRM Auth Audit Log` GROUP BY event, path, reason ORDER BY event, path", as_dict=True))
EOF
```

**Pass criteria:**
- 5–10 distinct (event, path, reason) combinations expected (Phase 4/5 smoke from S25 left ~10 rows)
- All existing rows have `path='password'`
- Event names follow the dotted convention: `auth.login.success`, `auth.login.failed`, `auth.account_locked`, `auth.logout`
- No existing `path='pin'` rows (would be unexpected — that path doesn't exist yet)

**Banked design decision for A2:** PIN path uses **the same `event` names**, distinguished by `path='pin'`. Specifically:
- `auth.login.success` with `path='pin'`
- `auth.login.failed` with `path='pin'` + reason ∈ {`invalid_credentials`, `account_locked`, `missing_input`, `no_pin_configured`}
- `auth.account_locked` with `path='pin'` (independent lockout state per R6 decision)
- `auth.logout` shared (path stored as whatever path issued the session, read from `frappe.session.data.vecrm_login_path`)

**Banked design decision for A2 (independent vs shared lockout):**

**Independent.** A user might forget their password and need to keep PIN-logging-in via mobile. Locking out one path because of the other is bad UX. So `failed_pin_attempts` and `pin_locked_until` are SEPARATE columns from `failed_password_attempts` and `locked_until`. Mirror logic, separate state.

**Fallback if event-namespace has unexpected entries:** Document and adjudicate; possibly introduce a path-prefixed event scheme.

---

## §7 — R1: `_issue_session` source-read — parameterize vs parallel helper

**Question:** Is `_issue_session` in `vecrm/api.py` currently structured to accept an arbitrary `login_path`, or does it hardcode `"password"`?

**Why this matters:** Decides whether PIN auth reuses the same helper (with a path parameter) or gets a parallel helper that calls a shared lower-level primitive.

**Verification command (executor runs):**

```bash
cd ~/Documents/GitHub/vecrm
grep -n "_issue_session\|vecrm_login_path" vecrm/api.py
sed -n '/^def _issue_session/,/^def [^_]/p' vecrm/api.py | head -60
```

**Source-read targets:**
1. Signature of `_issue_session`
2. Where `vecrm_login_path` is set (line + value)
3. All callers of `_issue_session` (grep result)
4. Whether `frappe.session.data.vecrm_employee_role` is set inside `_issue_session` or by the caller

**Pass criteria — Option R1-A (parameterize, preferred):**
- `_issue_session` is called from a small, contained set of sites (currently just `login_with_password`)
- The `vecrm_login_path = "password"` line is a single statement inside `_issue_session`
- Refactoring to `def _issue_session(employee_doc, login_path: str)` is a 2-line diff (signature + the assignment)
- Caller updates: `_issue_session(emp)` → `_issue_session(emp, "password")` at all sites (likely 1 site)

**Pass criteria — Option R1-B (parallel helper, fallback):**
- If `_issue_session` is called from multiple sites that don't need parameterization
- If `_issue_session` has side effects that diverge between path types

**Banked decision rule:** If `_issue_session` has ≤2 callers AND `login_path` is set in exactly one place inside it AND no caller depends on the hardcoded `"password"` literal elsewhere → **Option R1-A**. Otherwise → R1-B.

**Recon report fields for R1:**
- Exact signature
- Exact line where `login_path` is set
- Full caller inventory
- Recommendation (A or B) with rationale

---

## §8 — R2: PIN hash algorithm — passlibctx default verification

**Question:** What algorithm does Frappe's `frappe.utils.password.passlibctx` use by default in v16.18.2? Is `password_hash` currently being hashed with this same algorithm?

**Why this matters:** PIN hashing should use the SAME algorithm as password (banked decision from prior turn). We verify the passlibctx default to confirm we can reuse it without re-configuration.

**Verification command (executor runs):**

```bash
# Source-read of Frappe's passlibctx setup:
ssh root@217.216.58.117 'docker exec vecrm-backend-1 cat /home/frappe/frappe-bench/apps/frappe/frappe/utils/password.py' | grep -A 10 "passlibctx\|CryptContext\|schemes"
```

Plus a runtime verification:

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
from frappe.utils.password import passlibctx
print({"schemes": passlibctx.schemes(), "default": passlibctx.default_scheme()})
EOF
```

**Pass criteria:**
- `default_scheme()` returns a recognized strong scheme (`pbkdf2_sha256`, `argon2`, or similar)
- `schemes()` lists the same scheme as the first entry
- A sample `passlibctx.hash("test")` produces a string starting with `$pbkdf2-sha256$` or `$argon2id$` or similar (algorithm identifier)
- We also verify that the existing `password_hash` for Test Sales Rep starts with the same algorithm prefix:

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
hash_val = frappe.db.get_value("VECRM Employee", "+91-9999900001", "password_hash") or ""
print({"prefix": hash_val.split("$")[1] if "$" in hash_val else "<malformed>", "length": len(hash_val)})
EOF
```

**Banked decision for A2:** Use `passlibctx.hash(pin)` and `passlibctx.verify(submitted_pin, stored_pin_hash)` — same primitive as `password_hash`. The Data fieldtype + same algorithm means the existing VECRM-LOCK-PASSWORD-FIELDTYPE-AVOIDANCE applies identically to PIN.

**Fallback if passlibctx default has changed:** Document and adjudicate. Unlikely — Frappe doesn't typically change crypto defaults across minor versions.

---

## §9 — R3: Permission floor verification (VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE)

**Question:** Does the shared portal user (Website User + Submitter + Approver) have sufficient perms on `VECRM Employee` and `VECRM Auth Audit Log` for the PIN endpoint to work?

**Why this matters:** This is the §10.1-shaped risk from S25 (which landed at Phase 5 instead of Phase 1.5). Per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE, the verification gate runs **NOW** (at recon close), not at A2 Phase 5 browser smoke.

**Verification command (operator runs):**

```bash
ssh root@217.216.58.117 'docker exec -i vecrm-backend-1 bench --site crm.vinayenterprises.co.in console' <<'EOF'
import frappe
print({dt: sorted([r["role"] for r in frappe.db.sql("SELECT DISTINCT role FROM `tabDocPerm` WHERE parent=%s", (dt,), as_dict=True)]) for dt in ["VECRM Employee", "VECRM Auth Audit Log"]})
EOF
```

**Pass criteria:**
- `VECRM Employee` shows `['System Manager', 'VECRM Admin', 'VECRM Approver', 'VECRM Submitter']` (matches the Lead/Inquiry/TV pattern)
- `VECRM Auth Audit Log` shows at minimum `['System Manager']` — and may need extension if it currently lacks Submitter/Approver

**Important nuance:** `login_with_pin` (like `login_with_password`) uses `frappe.db.set_value` for writes and bypasses standard perm checks because the **session-issue happens AFTER login**, not during. The shared portal user's perm floor only matters for endpoints called AFTER session-issue. Login itself runs under whatever the **incoming request** is authenticated as — which is Guest before login.

So R3's pass criteria is actually:
- **For read endpoints called from within a portal session** (post-login): the shared user's roles need read access to VECRM Employee and VECRM Auth Audit Log. Confirm.
- **For the login endpoint itself**: it's `@frappe.whitelist(allow_guest=True)` — bypasses perm checks for the endpoint call, then uses elevated DB primitives for the credential lookup and audit-write. Confirm by re-reading `login_with_password` source (overlaps with R1).

**Banked decision for A2:** If `VECRM Auth Audit Log` lacks Submitter/Approver perms, we add them in the same migration as the PIN-field-add migration. Either way the migration is small.

**Fallback if perms are missing:** Add to the A2 migration's coupled scope. No surprise at Phase 5.

---

## §10 — Recon report structure (executor delivers via `present_files`)

After Claude Code runs R1–R6, produce a recon report markdown with this structure:

```
# PD-S26-AUTH-PHONE-PIN — Recon Findings (R1–R6)

## R4 — VECRM Employee column inventory
- Columns: [verbatim list from DESCRIBE]
- Target columns absent: pin_hash ✓/✗, failed_pin_attempts ✓/✗, pin_locked_until ✓/✗, last_pin_login_at ✓/✗
- S25-shipped columns present: password_hash ✓/✗, ...
- Conclusion: [migration safe / collision risk]

## R5 — Phone format inventory
- Row 1: name=..., vecrm_phone=..., role=...
- Row 2: ...
- Row 3: ...
- Canonical format: [+91-9XXXXXXXXX or variant]
- Normalization helper needed: [yes/no, and shape]

## R6 — Audit-log event inventory
- Existing (event, path, reason, n) tuples: [list]
- All rows have path='password': [yes/no]
- Banked PIN event design: [list of new (event, path, reason) tuples]
- Lockout independence decision: [independent, per recon]

## R1 — _issue_session shape
- Signature: [verbatim]
- login_path set at line N: vecrm_login_path = "password"
- Callers: [grep result, 1 line per caller]
- Recommendation: [Option R1-A or R1-B]
- A2 diff size: [N lines]

## R2 — PIN hash algorithm
- passlibctx default_scheme: [name]
- passlibctx.schemes(): [list]
- Existing password_hash algorithm prefix in production: [e.g. pbkdf2-sha256]
- Decision: reuse passlibctx default for PIN ✓

## R3 — Permission floor verification
- VECRM Employee perms: [list of roles]
- VECRM Auth Audit Log perms: [list of roles]
- Gap identified: [yes/no, what gap]
- A2 action: [perm extension migration / no action needed]

## Overall conclusion
- A2 dispatch can proceed: [yes/no]
- Blockers: [list, or "none"]
- Banked design decisions ready for A2: [N count]
```

---

## §11 — Risk register for the recon itself

Per VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE, every §risk needs a verification gate. Recon-level risks:

### §11.1 — Risk: source-read produces inconsistent picture of `_issue_session`

**Verification gate (R1 close):** the grep result MUST list ≤3 callers of `_issue_session`. If more than 3, recon halts and we re-scope before A2.

### §11.2 — Risk: production VECRM Auth Audit Log has unexpected entries

**Verification gate (R6 close):** all rows MUST have `path='password'` (or null, indicating S25-era pre-path entries). Any `path='pin'` row would mean someone already shipped PIN auth and we're confused about session state.

### §11.3 — Risk: phone format is inconsistent in production

**Verification gate (R5 close):** all 3 rows MUST have name format matching a single regex. If formats differ (e.g., some with `+91-` and some without), we document each variant and adjust normalization scope.

---

## §12 — What happens after recon close

1. **Claude Code completes R1–R6**, produces recon-findings report
2. **Operator pastes findings to dispatcher** (this chat thread)
3. **Dispatcher adjudicates** each finding against pass criteria
4. **If all clear:** dispatcher authors **PD-S26-AUTH-PHONE-PIN A2 implementation dispatch** with all design questions pre-answered
5. **If any blocker:** we re-scope before any implementation work

The A2 dispatch will be a separate document (~300-400 lines) covering phases 0.5 (Frappe symbol verification) through 6 (PR + merge). Estimated A2 wall-clock: 4-6 hours backend-only, 6-8 hours including portal UI.

---

## §13 — Authorization checklist

Before Claude Code starts:

- [ ] Operator has reviewed this recon dispatch
- [ ] Operator confirms scope is correct (backend recon only; no UI work in this phase)
- [ ] Operator authorizes Claude Code to execute R1–R6 in order R4 → R5 → R6 → R1 → R2 → R3
- [ ] Operator commits to running the bench-console queries (R4/R5/R6) personally — Claude Code does not have VPS shell

**Operator runs:** R4, R5, R6 (3 bench-console queries) — outputs pasted to chat.
**Executor runs:** R1, R2 source-reads (local repo grep/sed + 1 VPS source-read for passlibctx). R3 has a console part the operator runs.

---

## §14 — Anti-drift guards specific to this recon

1. **Source-reads only.** Zero writes anywhere.
2. **No assumptions from memory.** R4 verifies columns; R5 verifies formats; R6 verifies events. Even if "we know" from S25, we verify.
3. **Single-statement bench-console queries only.** Per OBS-S26-B lesson, no for-loops in heredocs.
4. **Findings get cited from actual output, not paraphrased.** The recon report includes verbatim DESCRIBE output, verbatim grep output, verbatim role lists.

---

## §15 — Sign-off

**Dispatcher:** Claude (this chat)
**Authorization:** Awaiting operator paste of R4/R5/R6 outputs + Claude Code execution of R1/R2/R3 source-reads.

End of recon dispatch.
