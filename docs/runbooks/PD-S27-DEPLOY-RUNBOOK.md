# PD-S27-DEPLOY-RUNBOOK

**Status:** PERMANENT — canonical deploy procedure for vecrm Frappe app to production VPS
**Authored:** 2026-05-24 (S27 close)
**Supersedes:** All prior deploy documentation (PR #4 era runbooks were aspirational, never matched reality — see PD-S26-DOCS-DRIFT closure)
**Verified against:** S27 PR #19 (logout audit), S27 PR #20 (lead schema), S27 PR #21 (auth reset schema). Three consecutive successful deploys using this exact procedure.

---

## §0 — Scope and audience

This runbook describes the end-to-end procedure to deploy a merged PR from vecrm `main` to production at `crm.vinayenterprises.co.in`.

**Audience:** Operator (Ajay) running commands on Mac + VPS, with dispatcher (Claude chat) adjudicating each step.

**NOT in scope:**
- vecrm-portal deploys (those are Vercel auto-deploy, handled separately)
- Frappe-Helpdesk site deploys (separate stack at `frappe-helpdesk-backend-1`)
- Database migrations outside of vecrm app patches (handled by Frappe core)
- First-time site bootstrap (rebuild scripts in `docs/runbooks/rebuild/`)

---

## §1 — Preconditions

Before initiating a deploy, verify all of these:

### §1.1 — Mac-side ground truth

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm
git checkout main
git pull origin main
git status
git log --oneline -3
```

**Pass criteria:**
- ✅ On branch `main`, up to date with `origin/main`
- ✅ Working tree clean (no uncommitted changes)
- ✅ Top commit is the PR you intend to deploy (matches the squash-merge SHA from GitHub)

If any of these fail: do not proceed. Investigate before continuing.

### §1.2 — VPS-side ground truth

```bash
# RUN ON VPS (ssh vemio)
docker ps --filter "name=vecrm-backend-1" --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
curl -sI https://crm.vinayenterprises.co.in/ | head -1
docker images vecrm-custom --format '{{.Repository}}:{{.Tag}}\t{{.ID}}' | head -5
```

**Pass criteria:**
- ✅ `vecrm-backend-1` Up (some duration), using `vecrm-custom:latest`
- ✅ `HTTP/2 200` from curl — site responding
- ✅ `vecrm-custom:latest` has an image ID — note this for the rollback tag step

If site is already down or backend is failing, this runbook is the wrong procedure — recovery is a different operation.

### §1.3 — voucher_counter.py canonical sha

```bash
# RUN ON VPS
sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py
```

**Pass criteria:** sha matches the canonical value pinned in `VECRM-L8.md`. Current canonical (as of S27): `91556a7d07359d91f5d0fd61f27b849b5dc0d098012cc45357025575bcc572a9`.

If sha differs:
- **If the PR being deployed modified voucher_counter.py intentionally:** proceed to §4 (Containerfile sha gate update) AND update VECRM-L8.md with the new canonical sha
- **If voucher_counter.py was NOT intentionally modified:** halt and investigate — vendor drift or untracked change

---

## §2 — Pre-deploy backups

Both backups are non-destructive and take seconds. Always do both.

### §2.1 — Rollback image tag

Tag the currently-running image with a session-specific rollback label BEFORE building the new image. This is what makes "roll back in 10 seconds" possible.

```bash
# RUN ON VPS
CURRENT_IMAGE=$(docker inspect vecrm-backend-1 --format='{{.Image}}' | sed 's/^sha256://' | cut -c1-12)
docker tag $CURRENT_IMAGE vecrm-custom:<session-and-PR-tag>
docker images vecrm-custom --format '{{.Repository}}:{{.Tag}}\t{{.ID}}' | head -7
```

**Tag naming convention:** `s<N>-pre-pr<M>-rollback` (e.g., `s27-pre-pr21-rollback`). One tag per PR deployed. Inspect `docker images vecrm-custom` to see the audit trail of past deploys — typically 5-8 tags accumulate.

**Pass criteria:** Output shows the new rollback tag pointing at the same image ID as `vecrm-custom:latest`.

### §2.2 — Containerfile backup (only if §4 will edit it)

If you anticipate updating the Containerfile (sha-gate edit, see §4), back it up first:

```bash
# RUN ON VPS — only if Containerfile will be edited this deploy
cp /opt/vecrm/images/custom/Containerfile \
   /opt/vecrm/images/custom/Containerfile.backup-pre-<session>-$(date -u +%Y%m%dT%H%M%SZ)
```

If no Containerfile edit is needed (the common case — most PRs don't touch voucher_counter.py), skip this step.

---

## §3 — Vendor refresh (Mac → VPS rsync)

The VPS production build reads from `/opt/vecrm/vecrm-src/` (the vendored vecrm app source), NOT from any remote git. The vendor directory must be refreshed from the local Mac clone after each PR merge.

### §3.1 — Rsync invocation (canonical)

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm
rsync -av --delete \
  --exclude='.git' \
  --exclude='.github' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='node_modules' \
  ~/Documents/GitHub/vecrm/ \
  vemio:/opt/vecrm/vecrm-src/
```

**Critical excludes (per VECRM-LOCK-S13-VENDOR-NO-GIT):**
- `.git` — vendor MUST NOT contain a `.git` directory. The Containerfile additionally has a defense-in-depth `find apps -mindepth 1 -path "*/.git" -prune -exec rm -rf {} +` at the end of the build, but the rsync exclude is the primary defense.
- `__pycache__`, `*.pyc` — Python bytecode caches; not source, just bloat
- `.DS_Store`, `node_modules` — macOS junk + heavy artifacts

**`--delete` is required.** Without it, files removed in `main` would linger in the vendor copy, causing stale-code-in-production bugs. With it, the vendor mirror reflects `main` exactly.

### §3.2 — Verify vendor copy

```bash
# RUN ON VPS
ls -la /opt/vecrm/vecrm-src/vecrm/vecrm/doctype/<any-newly-added-doctype>/
ls -la /opt/vecrm/vecrm-src/vecrm/patches/<any-new-patch-family>/
tail -5 /opt/vecrm/vecrm-src/vecrm/patches.txt
sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py
```

**Pass criteria:**
- New files from the PR are present at expected paths
- `patches.txt` has the new patch registered (last few lines)
- voucher_counter.py sha matches §1.3 canonical

Files in the vendor copy are owned by `501:staff` (the Mac-side UID:GID). This is benign — `cp -a` in the Containerfile preserves ownership, but the subsequent build steps run as the `frappe` user inside the container and the bench install handles permissions during `pip install -e`. Banking as OBS for future docs but not blocking.

---

## §4 — Containerfile sha-gate update (CONDITIONAL)

The Containerfile at `/opt/vecrm/images/custom/Containerfile` includes a hardcoded sha256 check at the POSTINSTALL_GATE that asserts `voucher_counter.py`'s sha matches the canonical value pinned in VECRM-L8. **This is intentional** — it catches accidental vendor drift before code reaches production.

### §4.1 — When to update

Update the Containerfile sha **ONLY IF** the PR being deployed intentionally modifies `voucher_counter.py` (rare — voucher_counter.py is a deliberately stable allocator per VECRM-L8). For PRs that don't touch voucher_counter.py, skip §4 entirely.

### §4.2 — How to update

```bash
# RUN ON VPS — only if voucher_counter.py changed
# 1. Get the new canonical sha
NEW_SHA=$(sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py | cut -d" " -f1)
echo "New sha: $NEW_SHA"

# 2. Find the current sha embedded in the Containerfile
CURRENT_SHA=$(grep -oE '[a-f0-9]{64}' /opt/vecrm/images/custom/Containerfile | head -1)
echo "Current sha in Containerfile: $CURRENT_SHA"

# 3. Backup (per §2.2)
cp /opt/vecrm/images/custom/Containerfile \
   /opt/vecrm/images/custom/Containerfile.backup-pre-<session>-$(date -u +%Y%m%dT%H%M%SZ)

# 4. In-place sed replacement
sed -i "s/$CURRENT_SHA/$NEW_SHA/g" /opt/vecrm/images/custom/Containerfile

# 5. Verify
grep -n "$NEW_SHA" /opt/vecrm/images/custom/Containerfile
grep -n "$CURRENT_SHA" /opt/vecrm/images/custom/Containerfile  # should return nothing
```

### §4.3 — Also update VECRM-L8

If voucher_counter.py legitimately changed, the canonical sha pinned in `docs/architectural-locks/VECRM-L8.md` is now stale. Update it in the same commit as the deploy:

```bash
# RUN FROM MAC
cd ~/Documents/GitHub/vecrm
# Edit VECRM-L8.md, replace the sha
# Add to the next docs(s<N>) close commit
```

### §4.4 — Tracked Containerfile (FUTURE — PD-S28-CONTAINERFILE-TRACKED)

The Containerfile currently lives ONLY on the VPS at `/opt/vecrm/images/custom/Containerfile`, NOT in a tracked repo. This is operational debt — banked as PD-S28-CONTAINERFILE-TRACKED (P1). Future session will commit it to a tracked repo with a paired pin file. Until that ships, manual sed-update is the procedure.

---

## §5 — Build invocation

The build produces a new `vecrm-custom:latest` image with the vendor source baked in. Always `--no-cache` to force full rebuild — vendor changes are sometimes invisible to BuildKit's layer cache without it.

```bash
# RUN ON VPS
cd /opt/vecrm

LOG="/opt/vecrm/.<session>_<pr>_build_$(date -u +%Y%m%dT%H%M%SZ).log"
echo "Build log: $LOG"

nohup docker build --no-cache \
  --secret=id=apps_json,src=apps.json \
  --file=images/custom/Containerfile \
  --tag=vecrm-custom:latest \
  . > "$LOG" 2>&1 &

BUILD_PID=$!
echo "Build launched, PID=$BUILD_PID"
```

**Log naming:** Include session + PR for searchability later. Example: `.s27_pr21_build_20260524T053000Z.log`.

**`nohup` rationale:** Build takes 10-15 min. If your ssh session drops, the build keeps running. Reconnect, locate log via `ls -t /opt/vecrm/.*_build_*.log | head -1`, find PID via `pgrep -af 'docker build --no-cache'`.

**Apps.json secret:** The build mounts `apps.json` as a BuildKit secret rather than a layer. Per upstream `frappe_docker` convention.

### §5.1 — Polling the build

```bash
# RUN ON VPS — at T+3 min (post-apt, pre-vecrm-COPY)
tail -30 $LOG
ps -p $BUILD_PID

# RUN ON VPS — at T+8 min (vecrm gates should appear)
tail -50 $LOG | grep -E "VECRM_(FETCH|POSTINSTALL)_GATE|exporting|naming"
ps -p $BUILD_PID

# RUN ON VPS — when ps reports gone (build complete)
tail -50 $LOG
docker images vecrm-custom --format '{{.Repository}}:{{.Tag}}\t{{.CreatedSince}}\t{{.ID}}' | head -3
```

**Observed timings (S27 PR #19/20/21 deploys):**
- T+0 to T+3 min: apt installs, Python setup, Node setup
- T+3 to T+5 min: bench setup, frappe + crm installs
- T+5 to T+8 min: vecrm install + gates (these are the critical steps)
- T+8 to T+12 min: backend stage assembly, asset bundling
- T+12 to T+15 min: image export (45-75s) + naming

Total: 10-15 min wall-clock. Faster on subsequent builds (BuildKit caches some lower layers regardless of `--no-cache` on the specific build step).

### §5.2 — Gate adjudication

**VECRM_FETCH_GATE:** Checks 6 specific canary files are present in the COPYed build context. If FAIL, the rsync is incomplete or a canary file was renamed/moved. The success message says "138 files in context, allocator+4 L1 controllers present" — the "4 L1 controllers" text is informational, not a count assertion. New controllers don't break this gate.

**VECRM_POSTINSTALL_GATE:** Checks the same 6 canary files are present AFTER `pip install -e` (defense against `--soft-link` symlink installs that leave hollow targets). Also asserts:
- `voucher_counter.py` sha matches Containerfile-embedded canonical
- Python import resolves: `import vecrm, vecrm.vecrm.voucher_counter` works
- `apps.txt` is exactly `frappe\ncrm\nvecrm` (catches concatenation bugs)
- Each app named in `apps.txt` is a real directory

**Stale success-message text (OBS-S27-X):** The POSTINSTALL_GATE success message ends with "6 controllers present" — this number has not been updated as controllers were added across sessions. It is informational, not a count assertion. Future Containerfile cleanup (in PD-S28-CONTAINERFILE-TRACKED) should rephrase to "<N> canary files present" for clarity.

### §5.3 — Build failure recovery

If `VECRM_FETCH_GATE FAIL`: a canary file is missing from the vendor copy. Re-rsync, verify with §3.2 probes, retry build.

If `VECRM_POSTINSTALL_GATE FAIL: voucher_counter.py sha mismatch`: see §4 — update the Containerfile sha to match the vendor's canonical sha.

If build succeeds but exit code is non-zero: tail the log to find the failing step. Common culprits: pip install timeout (transient), asset build OOM (need 12GB+ RAM — already addressed in S19 VPS upgrade).

If build process is killed mid-run by OOM: free memory (`docker system prune -af`), confirm 12GB+ RAM, retry.

---

## §6 — Container recreate

After successful build, swap the running container to the new image.

```bash
# RUN ON VPS
cd /opt/vecrm
docker compose up -d --force-recreate backend
```

**`--force-recreate backend` recreates only the backend service.** Sibling services (db, redis-cache, redis-queue, scheduler, queue-long, queue-short, frontend, websocket) keep running unchanged. Brief ~10-30s downtime on `crm.vinayenterprises.co.in` while the new backend container starts.

The `configurator` container will Exit (0) — that's expected; it's a one-shot init container that runs and exits.

The orphan-containers warning about `vecrm-redis-queue-1`, `vecrm-db-1`, `vecrm-redis-cache-1` is benign — those are vemio-* siblings sharing the compose project namespace.

### §6.1 — Post-recreate verification

```bash
# RUN ON VPS
docker inspect vecrm-backend-1 --format='{{.Image}}'
docker ps --filter "name=vecrm-backend-1" --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
curl -sI https://crm.vinayenterprises.co.in/ | head -1
```

**Pass criteria:**
- ✅ `docker inspect` shows the new image sha (matches the manifest list from build log)
- ✅ `docker ps` shows `Up <few seconds>`, image `vecrm-custom:latest`
- ✅ `HTTP/2 200` from curl

If site doesn't respond after 60s: `docker logs vecrm-backend-1 --tail 100` to investigate. Common causes: Frappe boot failure (check site_config.json), migration pending (next step), bench corruption (rare — rollback via §10).

---

## §7 — Migrate

Run `bench migrate` to apply any new patches and sync doctype changes.

```bash
# RUN ON VPS
docker exec vecrm-backend-1 bash -c \
  'cd /home/frappe/frappe-bench && bench --site crm.vinayenterprises.co.in migrate'
```

**Expected sections in output (in order):**

1. `Migrating crm.vinayenterprises.co.in`
2. `Updating DocTypes for frappe : [...] 100%`
3. `Updating DocTypes for crm : [...] 100%`
4. `Updating DocTypes for vecrm : [...] 100%` — vecrm doctypes synced from JSON definitions
5. `Executing vecrm.patches.v1_X.<patch_name> in crm.vinayenterprises.co.in (_<hash>)` — per registered patch
6. The patch's own `print()` output (typically the docstring + assertions, per PR #20/21 pattern)
7. `Success: Done in <X>s`
8. `Syncing jobs / fixtures / dashboards / customizations / languages`
9. `Updating Dashboard for <app>` lines
10. `Removing orphan <doctype/workspace/dashboard/page/report/notification/...>` lines (typically all "0 removed")
11. `Updating installed applications`
12. `Executing after_migrate hooks`
13. `Queued rebuilding of search index for crm.vinayenterprises.co.in`

**Pass criteria:** No `ERROR` or `TRACEBACK` anywhere. All patches show `Success: Done in <X>s`.

### §7.1 — Patch verbose output

The PR #20 and #21 patch conventions cause the patch's docstring to print at the start of `execute()`. This is informational verbose output — not a bug. Example from PR #21:

```
PD-S28-AUTH-RESET-SCHEMA: Create VECRM Auth Reset Token doctype.

Forward patch -- reloads the doctype definition into the database,
creating the `tabVECRM Auth Reset Token` table if it doesn't exist,
and asserts the table is present with the expected columns.
...

PD-S28-AUTH-RESET-SCHEMA: add_auth_reset_token_doctype
  VECRM Auth Reset Token doctype registered, all columns present, unique constraint active, 0 rows.
Success: Done in 0.067s
```

The pattern is: docstring print → identifier print → assertion result print → frappe "Success" line. Look for the assertion-result line specifically — it's the explicit "the work succeeded" signal.

### §7.2 — Migrate failure recovery

If a patch raises `frappe.throw` inside `execute()`:
- The migrate halts at that patch
- Earlier patches in the same migrate run are committed
- The failed patch is NOT marked as applied (will retry next migrate)

Recovery:
- Investigate the assertion that failed
- If recoverable: fix the data/state, re-run migrate (the patch will retry)
- If unrecoverable: run the paired rollback (per VECRM-L22), then redesign the patch

If a patch raises an unhandled exception (Python error, not `frappe.throw`):
- Same behavior as above, but the error message may be less clear
- Check `frappe.log` for the full traceback

---

## §8 — Smoke verification (per-PR)

After migrate succeeds, run smokes appropriate to the PR.

### §8.1 — Schema PR smoke pattern

For PRs that add columns or doctypes (PR #20, #21):

```bash
# RUN ON VPS
docker exec vecrm-backend-1 bash -c '
DB_PASS=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_password\"])")
DB_NAME=$(python -c "import json; print(json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\"))[\"db_name\"])")
DB_HOST=$(python -c "import json; cfg=json.load(open(\"/home/frappe/frappe-bench/sites/crm.vinayenterprises.co.in/site_config.json\")); print(cfg.get(\"db_host\", \"db\"))")
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "DESCRIBE \`<table>\`;"
mysql -h "$DB_HOST" -u "$DB_NAME" -p"$DB_PASS" "$DB_NAME" -e "SELECT COUNT(*) FROM \`<table>\`;"
'
```

For new doctypes, also check unique indexes:

```bash
mysql ... -e "SHOW INDEX FROM \`<table>\` WHERE Column_name = \"<unique_col>\";"
```

For schema-only-no-backfill PRs, expect COUNT = 0 (PR #21) or unchanged (PR #20 had backfill = 13).

**Note: Frappe v16 adds 4 standard metadata columns to every doctype** (`_user_tags`, `_comments`, `_assign`, `_liked_by`). Account for these in column-count predictions.

**Note: Frappe may bump Data field length to a minimum (typically 64).** Specifying `length: 45` in JSON may result in `varchar(64)` in the actual table. Functionally equivalent for IP addresses (45 chars max for IPv6), but worth noting.

### §8.2 — Data-write PR smoke pattern

For PRs that change how data is written (PR #19 added `path` to logout audit; PR #20 added `creating_employee` to leads):

Exercise the actual code path that should write the new data (login + logout for audit; lead creation for employee attribution), then probe the database for the expected row shape.

### §8.3 — bench console heredoc pattern

For smoke tests that need Python (insert/read/update/delete round-trips):

```bash
docker exec vecrm-backend-1 bash -c '
cd /home/frappe/frappe-bench && bench --site crm.vinayenterprises.co.in console <<"PYEOF"
import frappe
# ... test code ...
# Final line must be a print() or naked expression to show output
PYEOF
'
```

**VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION:** Frappe v16 `bench console <<EOF` works when module-level code is used (NOT function-wrapped). All imports + references must share the same globals dict. Errors of the form "name 'frappe' is not defined" inside a function wrapper indicate a scoping bug — refactor to module-level.

---

## §9 — Closing comment

After all smokes pass, paste in chat (or commit to handover doc):

1. PR merge commit SHA on `main`
2. New production image ID (post-recreate `docker inspect`)
3. Migrate output assertion line (the patch's success-print)
4. Smoke output(s)
5. Total deploy duration (build start → smoke complete)
6. Any deviations from this runbook

This is the audit trail. Future "did the deploy happen?" questions are answered by grepping for these in handover docs.

---

## §10 — Rollback procedure

If anything post-deploy is broken (site down, migration data corruption, regression), rollback in two commands:

```bash
# RUN ON VPS — emergency rollback
docker tag vecrm-custom:<session-pre-tag> vecrm-custom:latest
docker compose up -d --force-recreate backend
```

Example, rolling back PR #21:
```bash
docker tag vecrm-custom:s27-pre-pr21-rollback vecrm-custom:latest
docker compose up -d --force-recreate backend
```

**Time to rollback: ~10-15 seconds** (image tag + container recreate). The old image is preserved as a tagged docker image; no rebuild needed.

### §10.1 — What rollback CAN recover

- ✅ Code regressions in vecrm app (controllers, API methods, doctype JSONs)
- ✅ Hooks.py changes
- ✅ Static asset changes
- ✅ Container behavior changes

### §10.2 — What rollback CANNOT recover

- ❌ Database schema changes (new columns, new tables) — these are NOT in the image; they're in the MariaDB volume. Rolling back the image leaves the new schema in place.
- ❌ Data writes (backfills, audit rows added by the patch)
- ❌ Migrations applied to other apps (frappe/crm)

For schema-bearing PRs, rollback procedure is:
1. Rollback image (Steps above) — gets old code running
2. Manually invoke the patch's paired rollback (per VECRM-L22):
   ```bash
   docker exec vecrm-backend-1 bash -c \
     'cd /home/frappe/frappe-bench && bench --site crm.vinayenterprises.co.in execute vecrm.patches.v1_X.rollback_<patch_name>.execute'
   ```
3. Verify schema is reverted

Paired rollbacks exist for every schema-bearing patch per VECRM-L22. They are NOT registered in `patches.txt` — they are invoked manually only for recovery.

---

## §11 — Known failure modes

Common deploy issues and their diagnostics, from S15-S27 experience.

### §11.1 — Containerfile sha mismatch (false positive)

**Symptom:** `VECRM_POSTINSTALL_GATE FAIL: voucher_counter.py sha mismatch got=<X> expected=<Y>` where the new sha is correct and voucher_counter.py is the right file.

**Cause:** Containerfile embedded sha is stale (the canonical was updated in VECRM-L8 but the Containerfile wasn't updated in lockstep).

**Fix:** §4 — update Containerfile sha to match the new canonical.

### §11.2 — Vendor copy stale

**Symptom:** Build succeeds, recreate succeeds, migrate runs old code OR the new patch isn't executed.

**Cause:** rsync was skipped or failed silently.

**Fix:** Re-run §3 rsync, verify §3.2 probes show new files. Rebuild + recreate + migrate.

### §11.3 — OOM during build

**Symptom:** Build process killed by OOM-killer; log truncates abruptly with no error.

**Cause:** Build needs ~10GB RAM peak (vite step). VPS was upgraded to 12GB in S19; if RAM is now lower (Contabo plan changed?), this can recur.

**Fix:** Confirm RAM via `free -m`. If <12GB, escalate to Contabo for upgrade. Workaround: stop non-essential services temporarily during build.

### §11.4 — Migrate hangs on `Updating DocTypes`

**Symptom:** `Updating DocTypes for vecrm : [........] X%` hangs indefinitely.

**Cause:** Likely a JSON syntax error in a newly-added doctype JSON, or a circular Link reference.

**Fix:** `docker exec vecrm-backend-1 bash -c 'cd /home/frappe/frappe-bench && python -c "import json; json.load(open(\"/home/frappe/frappe-bench/apps/vecrm/<doctype>.json\"))"'` — catches JSON syntax. For Link references, inspect doctype JSON for fieldtype=Link.

### §11.5 — Site returns 500 after recreate

**Symptom:** `curl https://crm.vinayenterprises.co.in/ | head -1` returns `HTTP/2 500` or similar.

**Fix:** `docker logs vecrm-backend-1 --tail 200`. Common: `ImportError` from a missing or misnamed Python module in vecrm (the gates catch most of these at build time; runtime imports are caught here). Verify the doctype controller has the expected class name (e.g., `class VECRMAuthResetToken(Document)` not `class AuthResetToken(Document)`).

### §11.6 — Type-annotation failure (Frappe v16-specific)

**Symptom:** Frappe boot fails with `frappe.exceptions.ValidationError: Method X is not type-annotated` or similar.

**Cause:** Frappe v16's `require_type_annotated_api_methods` hook (set in hooks.py) rejects API methods without full type annotations.

**Fix:** Add type annotations to all `@frappe.whitelist()` methods in `vecrm/api.py`. Document `Document` subclass methods don't need annotations (only API methods do).

---

## §12 — Worked example: S27 PR #21 deploy (2026-05-24)

Canonical demonstration of this runbook executing end-to-end. Use as reference for future deploys.

### Inputs

- PR: #21 (PD-S28-AUTH-RESET-SCHEMA)
- Squash-merge SHA on main: `6d46b0d`
- Previous main HEAD: `5cd656e` (PR #20)
- Schema change: new `VECRM Auth Reset Token` doctype, no voucher_counter.py change
- Containerfile edit needed: NO

### Execution log (timings approximate, wall-clock)

| Step | Detail | Duration |
|---|---|---|
| §1 Mac ground truth | `git pull`, fast-forward to `6d46b0d`, working tree clean | 30s |
| §1 VPS ground truth | `vecrm-backend-1 Up 9 hours`, HTTP/2 200, image `ae202a2ef14b` | 15s |
| §2.1 Rollback tag | `vecrm-custom:s27-pre-pr21-rollback` → `ae202a2ef14b` | 5s |
| §2.2 Containerfile backup | SKIPPED — no sha change | 0s |
| §3 Rsync | 182 files inspected, 13 transferred, 45s total | 45s |
| §3.2 Vendor verify | 6 doctype + 3 patch files present, patches.txt registered, sha unchanged | 30s |
| §4 Containerfile sha | SKIPPED — voucher_counter.py unchanged | 0s |
| §5 Build | `--no-cache` build, gates at T+3.5 min, export at T+4 min | ~4 min |
| §6 Recreate | `docker compose up -d --force-recreate backend`, Up in 6.3s | 30s incl. verify |
| §7 Migrate | Patch fired with assertion: "VECRM Auth Reset Token doctype registered, all columns present, unique constraint active, 0 rows" | ~15s incl. all hooks |
| §8 Smoke 1 | DESCRIBE + SHOW INDEX + COUNT — all pass | 10s |
| §8 Smoke 2 | bench console insert + read + cleanup — round-trip clean | 30s |
| §8 Smoke 3 | bench console duplicate insert — `UniqueValidationError` raised | 30s |
| §9 Closing comment | New image `a05637cd2be5`, schema verified, 0 rows | — |

**Total deploy duration: ~7 min wall-clock** (faster than S27 PR #19/20 deploys which were ~12-15 min each — vendor was already largely in place, only PR #21's files were new; Containerfile didn't need editing).

### Observations from this deploy

- The "6 controllers" success message in POSTINSTALL_GATE is now misleading (7 controllers post-PR #21). Banked as OBS-S27-X.
- Frappe v16 adds 4 standard metadata columns to all doctypes (`_user_tags`, `_comments`, `_assign`, `_liked_by`) — observed in DESCRIBE output. Banked as OBS-S27-Z.
- Specified `length: 45` for `ip_address` in JSON; actual table shows `varchar(64)`. Frappe v16 min-length behavior. Banked as OBS-S27-AA.
- Patch's `print()` of the docstring at start of execute() is informational verbose output (carried from PR #20 convention). Banked as OBS-S27-Y.

---

## §13 — Locks referenced by this runbook

- **VECRM-L8** — voucher_counter.py canonical path + sha
- **VECRM-L13** — branch-first commits, squash-merge + branch deletion
- **VECRM-L22** — atomic schema migrations with assertions + paired rollback file
- **VECRM-L23** — narrow build context per worker
- **VECRM-L24** — file-scope scp only (no `scp -r` for file edits)
- **VECRM-L26** — always `\d <table>` (or DESCRIBE) before SQL probe
- **VECRM-L27** — verify history/inventory at every layer-transition checkpoint
- **VECRM-LOCK-S13-VENDOR-NO-GIT** — vendor directory must not contain `.git`
- **VECRM-LOCK-BENCH-CONSOLE-SCRIPTED-EXECUTION** — module-level code only in `bench console <<EOF` heredocs
- **VECRM-LOCK-VPS-PATH-CONVENTIONS** — `/opt/vecrm/` is frappe_docker, `/opt/vecrm/vecrm-src/` is the vendored vecrm app (BANKED S27)
- **VECRM-LOCK-CONTAINERFILE-SHA-MAINTENANCE** — update Containerfile sha-gate when canonical voucher_counter.py changes (BANKED S27)
- **VECRM-LOCK-PORTAL-SHARED-PRINCIPAL** — auth principal is shared `vecrm-portal` user; per-rep identity in `tabVECRM Employee` (BANKED S27)

---

**End of runbook.**

Future updates: when the Containerfile is committed to a tracked repo (PD-S28-CONTAINERFILE-TRACKED), this runbook gets an update covering the tracked-file procedure. Until then, manual sed-update per §4 is canonical.
