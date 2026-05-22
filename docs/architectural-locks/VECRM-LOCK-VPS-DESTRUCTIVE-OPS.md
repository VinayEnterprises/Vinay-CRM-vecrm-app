# VECRM-LOCK-VPS-DESTRUCTIVE-OPS

**Status:** ACTIVE (formal lock)
**Earned:** S23
**Promoted from:** Operator-driven directive (no OBS predecessor)
**Governs:** All VPS operations during VECRM development sessions

---

## Lock statement

VPS operations during VECRM sessions are scoped by destructive-vs-additive and by container-namespace. Specifically:

**VECRM-scoped operations Claude Code MAY perform without special authorization:**
- All VPS reads: `frappe.get_meta`, `frappe.db.get_value`, `frappe.get_all`, `docker ps`, file viewing, any `bench execute` of read-only Frappe functions
- Additive deploys: `scp` + `docker cp` of NEW code files to `vecrm-*` containers, `bench migrate` for new doctype registration, `docker restart vecrm-backend-1` for code reload
- Container restarts on `vecrm-*` containers (vecrm-backend-1, vecrm-frontend-1, vecrm-websocket, vecrm-queue-short, vecrm-queue-long, vecrm-scheduler, vecrm-mariadb, vecrm-redis-cache, vecrm-redis-queue)
- Cleanup of ferry residue: removing `/tmp/*.py` from VPS host, removing diagnostic scripts from container after §6 hard-gates

**Destructive operations Claude Code MUST request explicit dispatcher authorization for:**
- `rm` of any file inside a container or on VPS host
- SQL `DELETE`, `DROP`, `TRUNCATE`
- `frappe.delete_doc`, `frappe.db.sql("DELETE ...")`, `frappe.db.sql("DROP ...")`
- `docker rm` (container removal)
- `docker exec <container> rm`
- Any command that removes data or files

**Operations Claude Code MUST NOT perform under any circumstances:**
- Touching any non-`vecrm-*` container (especially `vemio-*` containers)
- Reading or writing to `vemio_*` or `glpi_*` database schemas
- Touching anything under `/opt/vemio/`
- Modifying the VEMIO Frappe site (`vemio.vinayenterprises.co.in`)
- Modifying shared infrastructure: nginx configs, certbot, system services, host-level firewall rules

## Rationale

VECRM and VEMIO share the same Contabo Mumbai VPS (217.216.58.117). They are isolated at:

- The Docker network level (separate compose stacks)
- The Frappe site level (`crm.vinayenterprises.co.in` vs `vemio.vinayenterprises.co.in`)
- The database level (separate Frappe site dbs)

But they share:

- SSH credentials (`root@217.216.58.117`)
- Docker socket access
- Filesystem (host paths)
- Network namespace at the host level

This means an agentic VPS-driver (Claude Code) operating in a VECRM session technically CAN reach VEMIO containers. The discipline that prevents accidents is this lock.

**VEMIO is live with real customer data:** 5 tenants in production (MSP root, Vinay HQ, AIA Engineering Limited, VEMIO Unmapped orphan-bucket, Datatech inactive). ~913+ tickets. Real MSP operations dependent on it.

Any unintended VEMIO impact from a VECRM session would:
- Affect real customer operations
- Be detectable but possibly not for hours
- Require restoration from backup (if recent backup exists)
- Damage operator's trust in the dispatcher/Claude-Code workflow

The lock exists to make this impossible by discipline.

## Authorization protocol for destructive operations

When Claude Code identifies a need for a destructive VECRM-scoped operation, the request to dispatcher MUST include:

1. **Exact command** to be executed (verbatim, including all flags)
2. **Scope** — which entities/rows/files will be affected
3. **Reason** — what problem this solves
4. **Backup approach** — how to preserve current state for restoration if needed
5. **Verification plan** — how to confirm the operation succeeded

Dispatcher response either:
- Authorizes (specifying any backup requirements)
- Asks for refinement (e.g., "narrow scope further")
- Declines (e.g., "do this on a feature branch first to test")

## Backup approaches (recommended by risk tier)

### Tier 1 — Targeted table backup (preferred for bounded operations)

For DELETE / TRUNCATE / DROP of single tables:

```sql
CREATE TABLE backup_<timestamp>_<table> AS SELECT * FROM <table>;
```

Pros: cheap, fast, restore-friendly via `INSERT INTO ... SELECT FROM backup_...`.
Cons: only covers data on that one table; doesn't protect against drops of other tables in same operation.

### Tier 2 — State recording (mandatory for ALL destructive ops, in addition to Tier 1)

Before any destructive op, dump current state of affected entities to chat or artifact:

```bash
# Example for a DELETE on rows in a specific table
docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.get_all" --kwargs '{...filter to match the DELETE criteria...}'
```

Captures intent and provides manual restoration path (recreate from the dumped data).

### Tier 3 — Full DB dump (only for schema migrations with high uncertainty)

```bash
docker exec vecrm-mariadb mysqldump <db_name> > /tmp/backup_<timestamp>.sql
```

Operator copies off-VPS. Slow, eats disk; reserve for genuinely high-risk operations like multi-table schema migrations or framework upgrades.

## Surfacing context (S23)

This lock was established during S23 because:

1. Claude Code had been running VPS commands directly throughout S23 (deploys, bench execute reads, docker restarts, scp+docker cp for ferry)
2. Operator raised the concern mid-session: "I would not want any unwanted changes or deletions to happen [on VEMIO]. This is a hard guardrail that needs to be followed."
3. Operator clarified the position: VPS access is OK (faster work); destruction without authorization is NOT OK.
4. Pattern that protected VEMIO through ~70 prior sessions: operator drove all VPS commands; Claude Code did recon + local code only. VECRM's S22-S23 sessions had relaxed that pattern without explicit re-authorization.

The lock formalizes the discipline going forward without revoking the speed benefits of Claude Code VPS access for additive work.

## Dispatcher discipline complement

A companion discipline note (banked as OBS-S23-I):

**Dispatcher must explicitly enforce this lock at session open when shared infrastructure is in scope.** Don't wait for operator to remind. Specifically:

- Session-open prompt should reference VECRM-LOCK-VPS-DESTRUCTIVE-OPS
- Any dispatch that includes destructive operations should explicitly call out the destructive-op authorization gate
- If a session is purely additive (e.g. new doctype + frontend work), state that explicitly so Claude Code doesn't need to ask for every routine deploy

## Enforcement points

1. **Pre-destructive-op check** — Claude Code internally checks: "is this command destructive?" before executing. If yes, must request authorization.

2. **Session-open prompt** — Reminds Claude Code that VECRM-LOCK-VPS-DESTRUCTIVE-OPS is active.

3. **Code review of session reports** — Dispatcher reviews Claude Code's reported commands at every phase boundary. Any unauthorized destructive command is a discipline failure to surface.

4. **Operator audit** — Operator can verify by reading session transcripts what commands ran.

## Examples

### Authorized without special request (additive)

```bash
# Deploy new controller
scp local-file root@217.216.58.117:/tmp/file
ssh root@217.216.58.117 'docker cp /tmp/file vecrm-backend-1:/home/frappe/.../file && rm /tmp/file'
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in migrate'
ssh root@217.216.58.117 'docker restart vecrm-backend-1'

# Read counter state
ssh root@217.216.58.117 'docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute "frappe.db.get_value" --args "[\"VECRM Voucher Counter\", {\"counter_key\": \"EV-26-27\"}, \"last_value\"]"'

# Cleanup ferry residue (additive cleanup of scripts Claude Code created)
ssh root@217.216.58.117 'docker exec vecrm-backend-1 rm -f /home/frappe/frappe-bench/apps/vecrm/vecrm/_s23_*.py'
```

That last one is acceptable because:
- It removes files Claude Code itself created (its own diagnostic scripts)
- It's scoped to a clear pattern (`_s23_*.py` matches only the diagnostic scripts)
- It's part of standard Phase D cleanup

### Requires explicit authorization (destructive)

```sql
-- Drop the phantom Sales Visit table (PD-S24-PHANTOM-SALES-VISIT-TABLE)
DROP TABLE tabVECRM Sales Visit;
```

Claude Code must request: "Authorization needed for DROP TABLE on tabVECRM Sales Visit. Scope: 0-row vestigial table. Reason: closes PD-S24-PHANTOM-SALES-VISIT-TABLE. Backup approach: Tier 2 state recording (dump SHOW CREATE TABLE result before drop; table has 0 rows so no data to capture). Verification: post-drop SELECT verifies table absence."

Dispatcher response: "Authorized. Proceed."

### Forbidden under all circumstances

```bash
# WRONG — touching VEMIO infrastructure from VECRM session
ssh root@217.216.58.117 'docker exec vemio-backend bench --site vemio.vinayenterprises.co.in execute frappe.db.get_value ...'

# WRONG — even reading vemio_db
ssh root@217.216.58.117 'docker exec vecrm-mariadb mariadb -u root -e "USE vemio_db; SELECT ..."'

# WRONG — host-level operation outside /opt
ssh root@217.216.58.117 'systemctl restart nginx'
```

## Related context

- VEMIO production tenant list and ticket counts (per session memory): MSP root, Vinay HQ, AIA Engineering Limited (first external live tenant per S63), VEMIO Unmapped (orphan-bucket, 11 tickets, 0 users), Datatech (is_active=false, 2 tickets, 0 users, pending operator decision)
- VECRM-DEPENDENCY-MAP.md PART 5.1 references this lock with the per-operation authorization table
- This lock supersedes any prior assumed "Claude Code may do anything on the VPS" pattern from S22's VECRM work

---

**End of VECRM-LOCK-VPS-DESTRUCTIVE-OPS**
