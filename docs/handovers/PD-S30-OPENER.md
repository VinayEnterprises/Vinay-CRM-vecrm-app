# PD-S30-OPENER

**Paste this as the first message of the next fresh conversation. Append the S29 close handover inline below if context space allows.**

---

I am continuing VECRM development. This is Session 30 (S30). Please read the orientation below, then perform the standard cold-check before we begin any new work.

## Stack and context

- **Repos:** `vecrm` (backend, Frappe v16 custom app on Contabo VPS) and `vecrm-portal` (frontend, Next.js 16 / React 19 / TypeScript on Vercel)
- **Backend:** Frappe v16 at `crm.vinayenterprises.co.in`
- **Portal:** Next.js at `app.vinayenterprises.co.in`
- **VPS:** Contabo Mumbai, accessed via `ssh vemio` (Mac alias only)
- **Production state at S29 close:**
  - vecrm main HEAD: `<run git log --oneline -1>` (post-S29-close-merge)
  - vecrm-portal main HEAD: `e0111b8`
  - Close tag on vecrm: `s29-close`
  - All 7 PRs from S29 merged
  - Both auth surfaces (password + PIN) verified working end-to-end in production for the first time

## What just happened in S29

7 PRs across both repos. 3 Workstreams shipped (A: Lead scoping; C: Account self-service; auth-write-pattern-fix). 2 Workstreams deferred to S30 (B: PIN segmented input; D: Lead form mandatory fields).

A pre-existing auth-write bug surfaced during Workstream C UI smokes and was diagnosed + fixed in the same session — PIN auth had been broken in production since S28 ship; password auth had been silently no-op'ing on resets since S28 (only working because of S25's one-time column bootstrap). PD-S29-AUTH-WRITE-PATTERN-FIX closes that.

Full S29 close handover at `docs/handovers/PD-S29-CLOSE-HANDOVER.md` on vecrm main.

## S30 cold-check (do this BEFORE any new work)

Run these 8 probes in order. Paste results. Don't propose any S30 work until cold-check is clean.

```bash
# 1. Confirm vecrm main is at S29 close
cd ~/Documents/GitHub/vecrm
git status   # expect: on main, no untracked, no unstaged
git log --oneline -3   # top should be the S29 close-docs commit, or PR #29 fix if close was via direct push
git tag | grep s29   # expect: s29-close

# 2. Confirm vecrm-portal main is at e0111b8
cd ~/Documents/GitHub/vecrm-portal
git status
git log --oneline -3   # top should be e0111b8 (PR #18 merge)

# 3. Confirm production backend is responsive
curl -sI https://crm.vinayenterprises.co.in/ | head -1
# Expected: HTTP/2 200

# 4. Confirm production portal is responsive
curl -sI https://app.vinayenterprises.co.in/ | head -1
# Expected: HTTP/2 200

# 5. Confirm production employee row state (auth columns)
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT name, LENGTH(password_hash) AS pwd_len, LENGTH(pin_hash) AS pin_len, failed_password_attempts, locked_until, failed_pin_attempts, pin_locked_until FROM \`tabVECRM Employee\` WHERE name = \"+91-9327547536\""'
# Expected: pwd_len=87, pin_len=87 (both populated post-S29 fix), all 4 lockout-state columns at baseline (0/NULL)

# 6. Confirm last S29 audit events
ssh vemio "docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e 'SELECT event, reason, employee, creation FROM \`tabVECRM Auth Audit Log\` WHERE employee = \"+91-9327547536\" ORDER BY creation DESC LIMIT 5'"
# Expected: most recent should show auth.login.success (PIN) + auth.change.pin.success from S29 close

# 7. Confirm rollback ladder
ssh vemio "docker images vecrm-custom --format '{{.Repository}}:{{.Tag}}\t{{.ID}}' | head -8"
# Expected: vecrm-custom:latest at PR #29 sha (3ac0489576d6 or similar from close)
# Plus: s29-pre-auth-write-fix-rollback, s29-pre-pr27-rollback, s28-* tags

# 8. Confirm Lead + Inquiry counts unchanged (data integrity)
ssh vemio "docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e 'SELECT (SELECT COUNT(*) FROM \`tabVECRM Lead\`) AS leads, (SELECT COUNT(*) FROM \`tabVECRM Inquiry\`) AS inquiries, (SELECT COUNT(*) FROM \`tabVECRM Employee\`) AS employees'"
# Expected: leads=14, inquiries=12, employees=1 (unchanged from S28)
```

**If any probe shows unexpected output, halt and surface before proceeding.**

## S30 candidate scope

Two deferred Workstreams from S29; operator picks one or both:

### Option A — Workstream D (PD-S29-LEAD-FORM-FIELDS)

**Lighter ship. Estimated ~2 hrs.**

Add 3 mandatory fields to New Lead form: `contact_number`, `contact_email`, `meeting_brief`. Migration approach LOCKED: schema-permissive (nullable cols) + code-mandatory + forward-only.

Affected:
- vecrm: `vecrm/vecrm/doctype/vecrm_lead/vecrm_lead.json` (add 3 fields) + `vecrm/patches/v1_2/add_lead_required_fields.py` + `vecrm/api.py::create_lead` (form-level mandatory enforcement)
- vecrm-portal: Lead create form add 3 fields; Lead detail render "—" for null on existing 14 Leads

Recon first per VECRM discipline. Then 2-PR shape (backend first, portal second).

### Option B — Workstream B (PD-S29-PIN-INPUT-SEGMENTED-6BOX)

**Heavier ship. Estimated ~2-3 hrs.**

6-segmented PIN input component. Apply to:
- LoginForm (login flow)
- /set-pin (new) — forgot-PIN reset confirmation
- /set-pin (confirm) — same
- /account ChangePinForm — currently uses single masked input (per S29 PR #18 deferral)

Backend tightening alongside:
- `complete_pin_reset` policy: 4-6 digits → exactly-6 digits
- `login_with_pin`: add length check (currently no length validation; allows arbitrary-length submission)

This brings full policy A consistency across all PIN-touching surfaces. Per OBS-S29-EE established in S29.

Recon first. Then 2-PR shape (backend tightening + portal segmented-input).

### Option C — Both in S30 (~4-5 hrs)

If energy permits, both Workstreams can ship in one S30. Order: D first (lighter, lower-risk), then B. Maintains the S29 σ-4 progression discipline.

### Option D — Strategic backlog item

Session-0-A (cohort testing) or Session-0-D (dashboard widgets) are multi-session strategic items. If S30 is a "different gear" session, one of these is appropriate.

## Recommended approach

Per VECRM discipline (recon-first, smoke-driven, branch-per-PR):

1. Cold-check (~10 min)
2. Pick one of the S30 candidates above
3. Author recon dispatch
4. Hand to Claude Code for recon
5. Review findings
6. Author B-phase dispatch
7. Hand to Code for implementation
8. Operator-driven deploy + smokes
9. Merge
10. S30 close (handover, pendency, S31 opener)

## Reference paths

- S29 close: `docs/handovers/PD-S29-CLOSE-HANDOVER.md`
- S29 pendency: `docs/handovers/VECRM-PENDENCY-S29-CLOSE.md`
- Active operating patterns: `docs/operating-patterns/` (especially `PD-S27-PORTAL-SCOPING-PATTERN.md`)
- Active dispatches: `docs/dispatches/` (S29 PD- prefixed files)
- Architectural locks: `docs/architectural-locks/`

## S29 banked observations to keep top-of-mind

- **OBS-S29-AAA** — Don't declare "found the bug" until ≥3 independent pieces of evidence converge
- **OBS-S29-CCC** — S25 canonical auth-write pattern: `passlibctx.hash + frappe.db.set_value(... update_modified=False)`. NEVER `update_password()` for VECRM Employee credential fields.
- **OBS-S29-III** — Production-evidence > one-shot probe for verification
- **OBS-S29-JJJ** — Console scripts work via `< file.py` redirection, not inline heredoc
- **OBS-S29-EE** — Policy decisions apply forward from decision moment; carry through to new entry points before old ones are tightened

Full list of 26 observations in S29 close handover §4.

---

**Begin with cold-check. Then I'll wait for operator decision on S30 scope.**
