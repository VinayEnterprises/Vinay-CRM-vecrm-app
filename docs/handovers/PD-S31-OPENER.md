# PD-S31-OPENER

**Session:** S31 (next)
**Predecessor:** S30 closed clean with 7 PRs shipped + recon for LEAD-OWNER-ATTRIBUTION authored
**Entry priority:** PD-S30-LEAD-OWNER-ATTRIBUTION B-phase (P1, Day-1)
**Secondary priorities:** Carried items from S30-close pendency (see `VECRM-PENDENCY-S30-CLOSE.md`)

---

## §1 — S31 opening sequence

**Step 1: Cold-check + probe (operator runs ~5 min):**

```bash
# vecrm main HEAD
cd ~/Documents/GitHub/vecrm
git checkout main && git pull origin main
git log --oneline -1
# EXPECT: PR #34 squash commit at HEAD (or whatever the post-S30 last merge was)

# vecrm-portal main HEAD
cd ~/Documents/GitHub/vecrm-portal
git checkout main && git pull origin main
git log --oneline -1
# EXPECT: b922863 (post-PR #21) or later

# Production container live
ssh vemio "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep vecrm-backend-1"
# EXPECT: vecrm-custom:latest, Up X seconds/minutes/hours

# Baseline counts
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT COUNT(*) AS leads FROM \`tabVECRM Lead\`; SELECT COUNT(*) AS inquiries FROM \`tabVECRM Inquiry\`"'
# EXPECT: 14 leads, 13 inquiries (S30-close baseline post-cleanup)

# Audit log post-S30 entries — confirms append-only is intact
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT COUNT(*) FROM \`tabVECRM Auth Audit Log\` WHERE creation > \"2026-05-25 15:00:00\""'
# EXPECT: ≥6 (the smoke entries from PR-B1; may be more if non-smoke logins occurred)

# Workers
ssh vemio "docker ps --format 'table {{.Names}}\t{{.Status}}' | grep vemio- | grep -v 'Up'"
# EXPECT: empty (all workers healthy)
```

**Step 2: Run F-1.4 probe (P0 BLOCKER for B-phase authoring)**

```bash
ssh vemio 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in mariadb -e "SELECT name, enabled, user_type FROM \`tabUser\` WHERE name = \"ajay@vinayenterprises.co.in\""'
```

Result interpretation:
- **Empty result → Case B**: Migration patch creates User row first (Website User type recommended; operator confirms type choice)
- **Non-empty result → Case A**: Straight UPDATE works

This single probe gates the entire B-phase. Run before any other work.

**Step 3: Run remaining LEAD-OWNER probes (F-1.1 through F-1.6, G-1.1 through G-1.3)**

Per recon findings doc §F.1 + §G. These are read-only sanity checks before authoring the B-phase. ~5 min total.

**Step 4: Answer the 14 ATT questions from recon findings §J**

ATT-1..3 (architecture), ATT-4..5 (validation), ATT-6..7 (surface scope), ATT-8..10 (migration), ATT-11..12 (coupling), ATT-13 (P0 blocker, addressed in Step 2), ATT-14 (audit migration policy).

Each ATT has a recon recommendation. Operator confirms or overrides.

**Step 5: Dispatcher authors PD-S30-LEAD-OWNER-ATTRIBUTION-B-PHASE-DISPATCH.md**

Based on:
- Findings doc (`docs/dispatches/PD-S30-LEAD-OWNER-ATTRIBUTION-findings.md` on local branch `recon/s30-lead-owner-attribution`)
- Operator probe results (Steps 2 + 3)
- 14 ATT answers

Dispatch will be 2 PRs:
- **PR-1 backend code fix**: 5 surgical edits in 4 files. ~25 lines net.
- **PR-2 migration**: v1_4 forward + rollback patches. Conditional shape per F-1.4 result.

---

## §2 — Carried context from S30

### Key facts to remember (high-value bankings)

**Frappe v16 API param convention (OBS-S30-N):**
```python
@frappe.whitelist()
def my_api(required_param: str, optional_param: str = None) -> dict:
    if not optional_param:
        frappe.throw(frappe._("Optional param is required."), frappe.ValidationError)
```
Never bare `optional_param: str` for params the API may need to report as missing.

**Three-layer deploy verification (VECRM-LOCK-DEPLOY-VERIFY-LIVE-CODE):**
1. Mac grep on Mac source post-edit
2. Vendor grep on `/opt/vecrm/vecrm-src/` post-rsync
3. Container grep on `/home/frappe/frappe-bench/apps/vecrm/` post-recreate

If any layer fails, deploy is unverified, not GREEN.

**Audit log is impartial witness (OBS-S30-Z):**
When credential-touching endpoints give unexpected HTTP, check audit log FIRST. Wire shape may be deliberately opaque per no-enumeration security design. Audit log tells the truth.

**mariadb safe-update mode (OBS-S30-M):**
DELETE/UPDATE on tabVECRM* tables requires `WHERE name = ...` (primary key) or another indexed column. NOT `WHERE company_name = ...`.

**OBS-S30-FF (Code's discipline):**
Code's instinct to investigate-instead-of-comply with dispatch checklists is excellent. Continue encouraging it. Dispatch is a guide; actual code wins per VECRM-LOCK-DISPATCH-SNIPPETS-ILLUSTRATIVE.

### S30 PRs shipped (for reference)

| # | Repo | Subject |
|---|---|---|
| #31 | vecrm | docs: full pendency restructure |
| #32 | vecrm | feat: Lead form mandatory fields backend |
| #33 | vecrm | fix: create_lead missing-field cases route via ValidationError |
| #34 | vecrm | fix: PIN policy tightening |
| #19 | vecrm-portal | feat: Lead form mandatory fields + PhoneInput + humanizeError |
| #20 | vecrm-portal | feat: PIN segmented 6-box input |
| #21 | vecrm-portal | fix: PinInput6Box visual polish |

### Production state at S30 close (S31 entry baseline)

- 14 Leads, 13 Inquiries (S30-close baseline post pre-S30 smoke cleanup)
- 5 VECRM Employees, 1 active (Ajay)
- `vecrm-custom:latest` running post-PR #34 image
- `vecrm-portal` on `b922863` (post-PR #21)
- All 4 voucher tables present
- 18/18 VEMIO workers healthy
- No real customer data seeded

### Items deferred to specific later sessions

| Session | Items |
|---|---|
| S31 | LEAD-OWNER-ATTRIBUTION B-phase (P1, Day-1) |
| S32 | LEAD-CONTACT-FIELDS + LEAD-ATTACHMENTS (P1+P2 batch), LEAD-INQUIRY-CLOSURE-UI (P1), ADMIN-USER-MGMT-PAGE (P1), ROLE-MATRIX-LOCK (P1) |
| S33 | LEAD-FOLLOWUP-WORKFLOW (3 sub-PRs, P1), EXPENSE-VOUCHER-PORTAL (P1), PWA-VALIDATION (P1) |
| S34+ | VOUCHER-APPROVAL-NOTIFICATIONS, VOUCHER-SUBMITTER-PORTAL, VOUCHER-APPROVER-PORTAL, WEEKLY-MEETING-REPORT, VEMIO-EMAIL-PIPELINE migration |

---

## §3 — S31-specific risks to watch

**Risk 1: ATT-13 F-1.4 result.**
If `ajay@vinayenterprises.co.in` does NOT exist as Frappe User, the migration becomes a 2-step (create User + UPDATE). The User type decision (Website User vs System User) matters for Desk-access semantics — operator confirms.

**Risk 2: Migration touches production data.**
15 Leads + 13 Inquiries get their `lead_owner` / `inquiry_owner` rewritten. Forward-only via L22 atomic schema migration pattern. Rollback patch restores `vecrm-portal@vinayenterprises.co.in`.

**Risk 3: Voucher audit migration policy (ATT-14).**
Recommendation: DO NOT migrate Voucher Audit Log historical rows. Audit is historical truth — even if "wrong," it's what happened. Future audit entries will be correct via code fix. Operator confirms or overrides.

**Risk 4: Multi-file backend touch.**
4 files getting edited; need careful single-PR discipline. NOT split into one PR per file.

---

## §4 — Specific reminders

- **Deploy commands** must cite verified runbook lines (OBS-S30-K → lock-candidate VECRM-LOCK-DEPLOY-COMMANDS-FROM-EVIDENCE). Use the post-S30 build log evidence as canonical.

- **Layer-3 verification** (`docker exec grep`) is mandatory at every deploy. The lock fires.

- **`gh pr view N --json state,mergedAt`** between merge and pull. Every time.

- **Baseline verification before branch** (OBS-S30-CC → lock-candidate). Code reads `git log -1` and confirms main HEAD matches dispatch's expected commit hash before branching.

- **Audit log first** for any confusing HTTP on credential endpoints (OBS-S30-Z).

- **Visual smokes need 3-axis check** (OBS-S30-II): card-vertical, card-horizontal, content-inside-card centering.

---

## §5 — What you DON'T do in S31

- Do NOT touch LEAD-CONTACT-FIELDS, LEAD-ATTACHMENTS, or FOLLOWUP-WORKFLOW yet. They batch with S32+.
- Do NOT redesign the auth surfaces (PIN, password, sessions) unless directly necessary for LEAD-OWNER fix.
- Do NOT introduce new shared form primitives unless triggered by a 3+ count.
- Do NOT touch the LEAD doctype schema unless LEAD-CONTACT-FIELDS lands in S31 (currently scheduled S32; can re-batch if S31 has unexpected slack).
- Do NOT chase PD-S30-PININPUT-HORIZONTAL-CENTER unless it can batch with another portal PR cleanly (P3 cosmetic — not Day-1 priority).

---

## §6 — Expected S31 deliverables

If everything goes smoothly:

**Item 1: LEAD-OWNER-ATTRIBUTION B-phase**
- PR-1 (vecrm backend code fix, ~5 surgical edits, no schema change)
- PR-2 (vecrm v1_4 migration patch + rollback)
- 4 smokes: Lead create, Inquiry create, Travel Voucher audit, Expense Voucher audit
- Production data migrated (15 + 13 rows updated)
- New Lead/Inquiry creation correctly attributes to `ajay@vinayenterprises.co.in`

**Item 2: Maybe — PD-S30-PININPUT-HORIZONTAL-CENTER**
- Single-line CSS fix if it batches naturally with any other portal touch

**Item 3: Maybe — Cleanup PR #4 docs drift (PD-S30-DOCS-DRIFT-PR4-RUNBOOK)**
- Documentation-only PR if context allows

---

**End of S31 opener.**
