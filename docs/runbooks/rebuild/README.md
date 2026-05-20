# vecrm image rebuild + deploy (VPS-side)

**Status:** Canonical per [VECRM-S20-A](../../architectural-locks/VECRM-S20-A.md) (revised in S21)
**Last verified:** S20 PR #5 build (image `47aa9e51…`), S20 PR #6 build (image `31383918a699…`), recon in S21 PD-S20-DOCS-DRIFT closure
**Audience:** Operator (Ajay) — and future-Ajay six months from now

## What this is

The canonical procedure for rebuilding the `vecrm-custom` image and deploying it to production. Runs entirely on the VPS at `/opt/vecrm/`. No Mac involvement.

Replaces the retired "Path B" Mac-buildx workflow (retired in S21 per VECRM-S20-A revision; preserved in git history at PR #4 commit `fe0e98d` if ever needed).

## Prerequisites

- VPS access: `ssh root@217.216.58.117`
- Free RAM on host ≥ 4 GB (build peaks around 3 GB on the vite step)
- vecrm-src on host at latest desired commit: `/opt/vecrm/vecrm-src/` synced to `origin/main`
- Disk: ≥ 2 GB free on `/var/lib/docker/` for the new image layer

## Build context

- Root: `/opt/vecrm/`
- Containerfile: `/opt/vecrm/images/custom/Containerfile` (multi-stage: base → builder → backend)
- apps.json: pins `frappe_crm` v1.71.3 only; vecrm vendored via `S13-COPY-NOT-CLONE` directive
- .dockerignore: excludes README.md, LICENSE, .gitignore, compose*.yaml (loose — see PD-S21-CTXBLOAT)
- Gates: `VECRM_FETCH_GATE` (6 controller files present in COPYed source), `VECRM_POSTINSTALL_GATE` (voucher_counter.py sha256 = `7ad2b3a32757346…`)

## Build procedure

Use `vecrm-build.sh` in this directory. The script captures the canonical invocation pattern.

```bash
ssh root@217.216.58.117
cd /opt/vecrm
bash /opt/vecrm/docs/runbooks/rebuild/vecrm-build.sh <session-tag>
# e.g. bash vecrm-build.sh s21-fix-staging
```

The script:
1. Verifies vecrm-src is at expected commit (operator confirms before invocation).
2. Logs the current `vecrm-custom:latest` image SHA for rollback bookkeeping.
3. Runs nohup-detached `docker build --no-cache` with the canonical args.
4. Polls build progress; reports completion + new image SHA.

Build runtime: ~4 min on 12 GB host. The build is nohup-detached so SSH disconnection does not abort it.

## Deploy procedure

Use `vecrm-deploy.sh` in this directory.

```bash
ssh root@217.216.58.117
bash /opt/vecrm/docs/runbooks/rebuild/vecrm-deploy.sh <new-image-tag> <session-tag>
# e.g. bash vecrm-deploy.sh s21-fix-staging s21-pre-fix-rollback
```

The script:
1. Preserves current `vecrm-custom:latest` as `vecrm-custom:<session-tag>` (rollback tier 1).
2. Retags the new image as `vecrm-custom:latest`.
3. Executes F-2 (`FLUSHALL vecrm-redis-cache-1`) BEFORE recreate.
4. Executes F-1 (4-f override chain `--no-build --force-recreate`).
5. Verifies fleet recovery (9 vecrm containers Up on new image SHA).
6. Verifies VECRM-L8 dual-surface allocator sha256.

## Rollback procedure (if something is wrong)

Three-tier rollback ladder maintained at every session boundary:

```bash
# Tier 1: roll back to the pre-fix image from this session
ssh root@217.216.58.117
docker tag vecrm-custom:s21-pre-fix-rollback vecrm-custom:latest
cd /opt/vecrm
docker compose -f compose.yaml -f overrides/compose.mariadb.yaml -f overrides/compose.redis.yaml -f overrides/compose.noproxy.yaml up -d --no-build --force-recreate
```

Tier 2 (previous-session rollback) uses `vecrm-custom:s<N-1>-pre-s<N>-rollback`. Same command pattern.

## Verification post-deploy

1. Fleet: `docker ps --format "{{.Names}}\t{{.Status}}" | grep -E "^vecrm-"` returns 9 lines, all Up.
2. Running image SHA: `docker inspect vecrm-backend-1 --format "{{.Image}}"` matches expected new SHA.
3. Allocator dual-surface: see `docs/operating-patterns/cold-check-template.md`.
4. Root URL: `curl -sI https://crm.vinayenterprises.co.in/ | head -1` returns `HTTP/2 200`.

## Reversal conditions

This procedure is canonical until VECRM-S20-A is revised again. Triggers for revision (see VECRM-S20-A §Reversal conditions): host RAM drops, Mac/local dependency needs to be added or removed, or Frappe build tooling changes.

## Provenance

- Authored: S21 PD-S20-DOCS-DRIFT closure, 2026-05-20
- Recon source: `/opt/vecrm/Containerfile`, `/opt/vecrm/apps.json`, `/root/.bash_history` lines 692, 1014, 1446, 1992, S20 build logs
- Replaces: `docs/runbooks/rebuild-pathB/` (retired in PR #8)
