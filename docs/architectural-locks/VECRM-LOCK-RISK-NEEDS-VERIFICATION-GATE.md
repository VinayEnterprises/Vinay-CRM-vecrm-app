# VECRM-LOCK-RISK-NEEDS-VERIFICATION-GATE

**Earned:** S25 (Phase 5.5 retrospective, OBS-S25-AV)
**Status:** ACTIVE
**Severity:** High (preventable defect — risk lands at wrong phase)

## Statement

Every `§risk` section in a VECRM dispatch document MUST include a concrete verification gate — a query, probe, or check that empirically proves the risk doesn't apply — and that gate MUST execute at the moment the risk becomes structurally concrete (NOT at the end of the dispatch when it manifests as a failure).

**Risk acknowledgment without verification is a structural defect.** Naming a risk in a dispatch §10 doesn't mitigate it; it just declares the dispatcher saw it coming. The mitigation is the gate.

## What "structurally concrete" means

A risk becomes structurally concrete at the phase where the decision that creates the risk lands. Not earlier (when the risk is theoretical), not later (when it manifests as a failure).

**S25 canonical case (OBS-S25-AR):**

- v2 dispatch §10.1 named the risk: "Existing endpoints may rely on shared-user permissions; portal sessions may break for surfaces not yet audited."
- The risk became structurally concrete at Phase 1.5, when the shared portal user's role membership was locked at Submitter+Approver only.
- The risk should have been verified at Phase 1.5 close with: `SELECT parent, role FROM tabDocPerm WHERE parent LIKE 'VECRM %' ORDER BY parent, role;`
- That one query would have surfaced the entire gap (VECRM Lead + VECRM Inquiry didn't have Submitter/Approver perms).
- Instead, the risk landed at Phase 5 Step 5.E (browser smoke) as `/api/leads` and `/api/inquiries` returning 403 Forbidden in production. Cost: ~30 minutes of Phase 5.5 work after the symptom was observed.

## Pattern (correct)

In dispatch §risk sections:

```markdown
### §10.1 — Existing endpoints may break under new permission floor

**Risk:** Shared portal user (Submitter+Approver) may lack perms on doctypes
some endpoints rely on.

**Verification gate (execute at Phase 1.5 close, before proceeding to Phase 2):**

```sql
SELECT parent AS doctype, role
FROM tabDocPerm
WHERE parent LIKE 'VECRM %'
ORDER BY parent, role;
```

**Pass criteria:** Every VECRM doctype touched by the portal (VECRM Lead,
VECRM Inquiry, VECRM Travel Voucher, VECRM Expense Voucher) has rows for
both VECRM Submitter and VECRM Approver.

**Fail action:** Add the missing perm rows via a coupled doctype JSON
edit before Phase 2 ships.
```

## Anti-pattern (WRONG — this caused OBS-S25-AR)

```markdown
### §10.1 — Existing endpoints may break under new permission floor

**Risk:** Shared portal user (Submitter+Approver) may lack perms on doctypes
some endpoints rely on.

**Mitigation:** Audit existing surfaces during browser smoke (Phase 5).
```

This is acknowledgment + deferred mitigation. The gap surfaces empirically four phases later.

## Why this matters operationally

- **Surface discovery is empirical.** You may name 3 risks; one of them lands. The verification gate is what proves which one.
- **Cost compounds.** A risk discovered at Phase 5 retroactively invalidates the work done in Phases 2-4 (in S25, the auth code was correct; only the doctype perms were wrong, but you don't know that until you smoke).
- **§risk → §verification-gate is a one-line code change in dispatch authoring.** It's cheap to author and removes a class of defects.

## Where this lock applies

- Every new dispatch document (A2, A3, etc.)
- Every recon report (R1-R6) that surfaces risks
- Every architectural-locks file (which often documents what could have been a §risk)

## When this lock can be relaxed

NEVER. A risk without a gate is not a risk that was managed; it's a risk that was named.

If a risk is genuinely "we'll know empirically when we get there" (e.g., visual UX preferences), reframe it as an explicit observation point (`§5.X — visual review checkpoint`) rather than a §risk.

## Related observations

- OBS-S25-AR — the §10.1 risk landing at Phase 5
- OBS-S25-AV — promoted to this lock
- OBS-S25-AW — risk-related dispatcher framing was structurally wrong (Travel Voucher mirror would have introduced submittable-only keys on non-submittable doctypes; would have been caught by a "validate doctype shape" gate at the mirror-decision moment)

## Application examples

### Example 1: Schema migration risk

```markdown
### §3.2 — Migration may fail mid-DDL

**Risk:** ALTER TABLE on a large table could fail partway, leaving
schema in inconsistent state.

**Verification gate (execute before deploying migration):**

```sql
-- 1. Verify migration runs cleanly on a copy of the table
CREATE TABLE temp_test_migration LIKE tabVECRM_Employee;
INSERT INTO temp_test_migration SELECT * FROM tabVECRM_Employee LIMIT 1000;
-- run forward migration against temp_test_migration
-- if clean, proceed; if errors, fix migration before deploying
```

**Pass criteria:** Migration runs cleanly against 1k-row sample. EXPLAIN
output reasonable.
```

### Example 2: External API dependency

```markdown
### §4.1 — Microsoft Graph API may rate-limit reset emails

**Risk:** During high-traffic period, password reset requests may exceed
Graph send limits.

**Verification gate (execute at Phase 4 close):**

```python
# Probe Graph current send quota; verify < 80% used
quota = graph_client.get("/users/{}/mailboxSettings/quota".format(sender_id))
assert quota["used"] / quota["limit"] < 0.8
```

**Pass criteria:** Quota usage < 80%. **Fail action:** Add internal
rate-limit before exposing endpoint to end users.
```
