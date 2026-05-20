# Path B — vecrm Image Rebuild (Mac amd64 → tarball → VPS load)

**Status:** Permanent rebuild path per [VECRM-S20-A](../../architectural-locks/VECRM-S20-A.md)
**Last verified:** S19 (proved end-to-end on Mac amd64 buildx), S20 (formalized as scripts + locked posture)
**Audience:** Operator (Ajay) — and future-Ajay six months from now

---

## TL;DR

You need to rebuild the vecrm Docker image. **Do not try to build on the VPS.** The host doesn't have enough RAM to complete the vite step ([VECRM-S19-C](../../architectural-locks/VECRM-S19-C.md)). Instead:

1. Build on a Mac (or any amd64-capable machine with ≥16 GB RAM and Docker buildx).
2. Export the image as a gzipped tarball.
3. scp the tarball to the VPS.
4. Load + retag + recreate on the VPS.

Two scripts automate this end to end:

- **`vecrm-rebuild-pathB.sh`** — runs on the Mac. Aligns the repo, audits the build context, builds the image, exports the tarball, prints scp instructions.
- **`vecrm-deploy-image.sh`** — runs on the VPS. Verifies the tarball, loads it, preserves the previous image as a rollback tag, retags as `:latest`, runs the F-2/F-1 recreate sequence, verifies post-deploy.

Both scripts are write-once, dry-runnable (`DRY_RUN=1`), and self-verifying. Each script honors the locks earned during S19 ([S19-A](../../architectural-locks/VECRM-S19-A.md), [S19-B](../../architectural-locks/VECRM-S19-B.md), [S19-E](../../architectural-locks/VECRM-S19-E.md)) and S20 ([S20-A](../../architectural-locks/VECRM-S20-A.md)).

---

## Why Path B exists

In S19, two consecutive `--no-cache` rebuild attempts on the 8 GB Contabo host failed with OOM kills at the vite step. Even with VEMIO stopped, the build peaked beyond available headroom (vite alone needed ~3.5 GiB; total build pressure exceeded ~6 GiB).

S19 pivoted to building on Ajay's 16 GB MacBook Air via `docker buildx --platform linux/amd64`. The build completed in ~5 minutes; the resulting image was exported as an 822 MB gzipped tarball, scp'd to the VPS, and loaded via `docker load`. Production was bought up on the new image with zero degradation.

S20 made this the permanent pattern. The host has since been upgraded to 12 GB (Contabo VPS 20 SSD tier), but Path B remains the standard for these reasons:

- **Isolation of build pressure from production.** Rebuilds no longer compete with VEMIO/vecrm/helpdesk for runtime memory.
- **Faster iteration.** Mac buildx (with native filesystem and BuildKit caching) is consistently faster than VPS builds even on identical hardware.
- **No risk of half-built production state.** Failed builds happen on the Mac, not the production host.
- **Eliminates the "rebuild causes production OOM" risk class entirely.**

See [VECRM-S20-A](../../architectural-locks/VECRM-S20-A.md) for the full decision context, including reversal conditions.

---

## Prerequisites

### On the Mac (build host)

| Requirement | Status check |
|---|---|
| macOS (any recent version) | `sw_vers` |
| Docker Desktop running, buildx available | `docker buildx version` |
| ≥16 GB RAM | Apple menu → About This Mac |
| `git`, `rsync`, `shasum`, `scp` | Standard on macOS |
| Local checkout of `Vinay-CRM-vecrm-app` at `~/Documents/GitHub/vecrm/` | `ls ~/Documents/GitHub/vecrm/.git` |
| SSH access to `root@217.216.58.117` with key auth | `ssh root@217.216.58.117 'echo ok'` |

### On the VPS (deploy target)

| Requirement | Status check |
|---|---|
| `/opt/vecrm/` exists with the compose chain | `ls /opt/vecrm/compose.yaml` |
| `vecrm-src` git clone at `/opt/vecrm/vecrm-src/` | `ls /opt/vecrm/vecrm-src/.git` |
| Existing `vecrm-custom:latest` image | `docker images vecrm-custom:latest` |
| All 9 vecrm containers running | `docker ps --filter 'name=vecrm-' \| wc -l` returns 10 (header + 9) |
| `vecrm-redis-cache-1` reachable | `docker exec vecrm-redis-cache-1 redis-cli ping` returns `PONG` |

If any of these fail, **stop and fix before proceeding.** Do not attempt a deploy on an unhealthy baseline.

---

## Phase 1 — Mac-side build

### Command

```bash
cd ~/Documents/GitHub/vecrm/docs/runbooks/rebuild-pathB
./vecrm-rebuild-pathB.sh <session-tag>
```

`<session-tag>` is your session label — e.g. `s21`, `s22`. Used in image tag and tarball filename.

**Example (dry-run first, then real):**

```bash
DRY_RUN=1 ./vecrm-rebuild-pathB.sh s21    # print steps without executing
./vecrm-rebuild-pathB.sh s21              # actual build
```

### What it does, in order

1. **Preflight** — verifies tools, repo existence, buildx availability. Aborts with distinct exit codes (2–13) if anything is missing.

2. **Repo alignment ([VECRM-S19-A](../../architectural-locks/VECRM-S19-A.md))** — `git fetch origin`, asserts `origin/main` ref exists, `git reset --hard origin/main`. The Mac's local branch may be stale; the script aligns it to GitHub-canonical truth before building.

3. **Build context minimum-set audit ([VECRM-S19-E](../../architectural-locks/VECRM-S19-E.md))** — parses every `COPY` and `ADD` directive in `images/custom/Containerfile`, derives the list of required paths, and verifies each one exists after the build context is staged. **Will not proceed if anything is missing.**

4. **Build context staging** — `rsync -a --delete` from `~/Documents/GitHub/vecrm/` to `~/vecrm-build/`, excluding `.git/` and `dist/`. The build context is rebuilt from scratch each run; nothing is preserved across runs except the dist output folder.

5. **apps.json manifest verification ([VECRM-S19-B](../../architectural-locks/VECRM-S19-B.md))** — positively asserts that `apps.json` references both `frappe` and `vecrm`. Won't proceed if manifest is wrong.

6. **Build** — `docker buildx build --no-cache --platform linux/amd64 --secret=id=apps_json,src=apps.json --file=images/custom/Containerfile --tag=vecrm-custom:<session-tag>-mac-build --load .`

   Takes ~5 minutes. Vite is the long pole at ~3.5 min. The `--secret` flag is essential — `apps.json` is mounted as a build secret, not baked into image layers.

7. **Export to tarball** — `docker save | gzip` to `~/vecrm-build/dist/vecrm-custom-<session-tag>-<stamp>.tar.gz`. Computes sha256 and writes it to a `.sha256` sidecar file. Expected size: ~800 MB gzipped.

8. **Print scp instructions** — exact commands to run for Phase 2.

### Output you should see

```
HEAD built:     47e26dad4c245632c3f17b0674721ef595800b43
Image tag:      vecrm-custom:s21-mac-build
Tarball:        ~/vecrm-build/dist/vecrm-custom-s21-<stamp>.tar.gz
Tarball sha256: <64-hex>
```

If any of these are empty or look wrong, **do not scp**. Investigate first.

### When it fails

| Symptom | Likely cause | Fix |
|---|---|---|
| `origin/main ref does not exist` | Repo's remote refspec is tag-only | Check `git remote -v`; ensure remote URL is correct |
| `MISSING: <path>` in audit | Build context staging incomplete OR Containerfile changed | Investigate the missing path; re-check what `COPY/ADD` directive references it |
| `apps.json MISSING reference to vecrm` | `apps.json` is wrong | Compare against last working version; ensure both `frappe` and `vecrm` are referenced |
| Build hangs at vite | Mac is under memory pressure | Quit other apps, ensure Docker Desktop has ≥8 GB allocated |
| `docker load` errors out | Tarball corrupted in transit | Re-verify Mac-side sha256; re-scp |

---

## Phase 2 — Transfer to VPS

```bash
# 1. Create the per-session staging dir on the VPS
ssh root@217.216.58.117 'mkdir -p /opt/vecrm/builds/<session-tag>/'

# 2. scp the tarball, its sha256 sidecar, and the deploy script
scp ~/vecrm-build/dist/vecrm-custom-<session-tag>-<stamp>.tar.gz \
    ~/vecrm-build/dist/vecrm-custom-<session-tag>-<stamp>.tar.gz.sha256 \
    ~/Documents/GitHub/vecrm/docs/runbooks/rebuild-pathB/vecrm-deploy-image.sh \
    root@217.216.58.117:/opt/vecrm/builds/<session-tag>/

# 3. Verify they landed
ssh root@217.216.58.117 'ls -la /opt/vecrm/builds/<session-tag>/'
```

Expected transfer time at typical home internet: ~3–5 minutes for an 800 MB tarball. Server-side disk space requirement: ~1 GB transient (tarball + unpacked image, until cleanup).

---

## Phase 3 — VPS-side deploy

### Command

```bash
ssh root@217.216.58.117
cd /opt/vecrm/builds/<session-tag>/
bash vecrm-deploy-image.sh <session-tag> <tarball-filename>
```

**Example (dry-run first):**

```bash
DRY_RUN=1 bash vecrm-deploy-image.sh s21 vecrm-custom-s21-20260601T120000Z.tar.gz
bash vecrm-deploy-image.sh s21 vecrm-custom-s21-20260601T120000Z.tar.gz
```

### What it does, in order

1. **Preflight** — confirms tarball and sha256 sidecar exist.
2. **Verify tarball sha256** — must match the sidecar. Aborts on mismatch (corrupted transfer or wrong file).
3. **Capture pre-deploy state** — records current `vecrm-custom:latest` SHA and running `vecrm-backend-1` image SHA for the rollback inventory.
4. **Preserve current `:latest` as rollback tag** — tags the current `:latest` as `vecrm-custom:s<N-1>-pre-s<N>-rollback`. This is the one-command rollback if anything goes wrong.
5. **Load new image** — `gunzip -c <tarball> | docker load`. Takes 30–60 seconds.
6. **Retag new image as `:latest`** — `docker tag vecrm-custom:<session-tag>-mac-build vecrm-custom:latest`.
7. **F-2 lock — FLUSHALL vecrm-redis-cache-1.** Eliminates stale cached state from the cache layer before bringing up the new code. **MUST happen before recreate, never after.**
8. **F-1 lock — coherent recreate via 4-f override chain `--no-build`:**
   ```
   docker compose \
     -f compose.yaml \
     -f overrides/compose.mariadb.yaml \
     -f overrides/compose.redis.yaml \
     -f overrides/compose.noproxy.yaml \
     up -d --no-build --force-recreate
   ```
9. **Post-deploy fleet check** — confirms 9 vecrm containers are running.
10. **Post-deploy dual-200 check** — confirms `http://127.0.0.1:8091/` returns 200 and a hashed asset URL returns 200.
11. **[VECRM-L8](../../architectural-locks/VECRM-L8.md) dual-surface allocator verification** — sha256s `voucher_counter.py` inside the running container AND in the VPS git clone; they must match.

### Output you should see (success)

```
VECRM-L8 dual-surface: PASS (match)
vecrm containers running: 9 (expected: 9)
Root URL status: 200 (expected: 200)
Hashed asset /assets/<hashed>.js: 200 (expected: 200)
Final image inventory:
  vecrm-custom:latest                       sha256:<new>
  vecrm-custom:s<session-tag>-mac-build     sha256:<new>
  vecrm-custom:s<N-1>-pre-s<N>-rollback     sha256:<old>
  ...
```

If anything above is wrong, **stop and surface before declaring deploy success.** Don't proceed to use the new image until adjudication is complete.

### Rollback (if deploy goes wrong)

The deploy script preserves the previous `:latest` as a rollback tag. Rollback is two commands:

```bash
docker tag vecrm-custom:s<N-1>-pre-s<N>-rollback vecrm-custom:latest
cd /opt/vecrm && docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.noproxy.yaml \
  up -d --no-build --force-recreate
```

Verify post-rollback the same way: dual-200, fleet count, allocator dual-surface. If rollback also fails, you're in incident territory — escalate, don't improvise.

---

## Cleanup

After a successful deploy, the per-session staging dir on the VPS can be archived or deleted:

```bash
# After confirming stability for at least a session, drop the tarball:
rm /opt/vecrm/builds/<session-tag>/*.tar.gz
# Keep the sha256 sidecar and deploy log for the audit trail.
```

Old rollback tags can be pruned periodically. Keep at least the most recent 2–3 (i.e. the rollback for the current `:latest` AND one prior, in case rollback itself reveals a regression that requires going back further):

```bash
# Inspect what's there:
docker images vecrm-custom

# Remove old tags by name (this only untags; the image layers stay if any tag remains):
docker rmi vecrm-custom:s<old>-pre-s<old+1>-rollback

# After untagging old versions, prune dangling layers:
docker image prune
```

---

## Reference: paths and conventions

| Item | Path |
|---|---|
| Mac repo checkout | `~/Documents/GitHub/vecrm/` |
| Mac build context (staged fresh each run) | `~/vecrm-build/` |
| Mac tarball output | `~/vecrm-build/dist/` |
| VPS clone (read-only for deploys) | `/opt/vecrm/vecrm-src/` |
| VPS compose chain | `/opt/vecrm/compose.yaml` + `overrides/*.yaml` |
| VPS per-session staging | `/opt/vecrm/builds/s<N>/` |
| Image tag (new build) | `vecrm-custom:s<N>-mac-build` |
| Image tag (production) | `vecrm-custom:latest` |
| Image tag (rollback) | `vecrm-custom:s<N-1>-pre-s<N>-rollback` |
| Containerfile | `images/custom/Containerfile` (relative to build context) |
| Build manifest | `apps.json` (relative to build context, passed as `--secret`) |

---

## Reference: related architectural locks

- [VECRM-L8](../../architectural-locks/VECRM-L8.md) — Allocator dual-surface verification (git = container)
- [VECRM-S19-A](../../architectural-locks/VECRM-S19-A.md) — Verify remote-tracking ref after `git fetch`
- [VECRM-S19-B](../../architectural-locks/VECRM-S19-B.md) — Positive verification of build manifest before rebuild
- [VECRM-S19-C](../../architectural-locks/VECRM-S19-C.md) — Original 8 GB host insufficient finding (now historical)
- [VECRM-S19-D](../../architectural-locks/VECRM-S19-D.md) — After 2 identical failures, pivot rather than retry
- [VECRM-S19-E](../../architectural-locks/VECRM-S19-E.md) — Build context minimum set derived from every COPY/ADD
- [VECRM-S19-F](../../architectural-locks/VECRM-S19-F.md) — Cross-session prose-vs-source corollary to L1
- [VECRM-S20-A](../../architectural-locks/VECRM-S20-A.md) — Permanent Path B posture; 12 GB host upgrade

---

## Reference: F-1 and F-2 locks (compose chain hygiene)

These locks were earned before S19 and are critical for deploy correctness:

- **F-1 (coherent recreate)** — Always use the full 4-f override chain `--no-build`. Partial override chains produce inconsistent network/volume/secret resolution. The `--no-build` flag prevents docker compose from attempting to rebuild locally (which would fail on the VPS per VECRM-S19-C anyway).

- **F-2 (Redis flush before recreate)** — `FLUSHALL vecrm-redis-cache-1` MUST happen before `docker compose up`. Stale cached state will cause the new code to read inconsistent data, producing subtle bugs that survive container restarts.

Both are baked into `vecrm-deploy-image.sh`. Do not bypass them.

---

## Change history

| Session | Change | Author |
|---|---|---|
| S19 | Path B proven end-to-end on Mac amd64 buildx | Ajay + Claude |
| S20 | Formalized as scripts + runbook; host upgraded 8→12 GB; posture locked permanent | Ajay + Claude |

Future revisions go here. If the Mac changes (e.g. new build host), or if the Containerfile structure changes (e.g. new required `COPY`), or if the compose chain shape changes — update this runbook AND the affected script.
