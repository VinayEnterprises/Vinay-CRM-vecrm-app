#!/usr/bin/env bash
# vecrm-deploy-image.sh — VPS-side Path B deploy
#
# Runs on the VPS (vemio-primary). Receives a tarball staged from the Mac
# rebuild script, verifies it, loads the image, preserves the current :latest
# as a rollback tag, retags the new image as :latest, and performs the
# F-1/F-2 coherent recreate.
#
# Locks honored:
#   F-2 — FLUSHALL vecrm-redis-cache-1 BEFORE recreate
#   F-1 — coherent recreate via 4-f override chain --no-build
#   VECRM-L8 — post-deploy allocator dual-surface verification
#   VECRM-S20-A — Path B is the permanent rebuild path
#
# Usage:
#   ./vecrm-deploy-image.sh <session-tag> <tarball-filename>
# Example:
#   ./vecrm-deploy-image.sh s20 vecrm-custom-s20-20260520T143000Z.tar.gz
#
# Environment overrides:
#   VECRM_BUILDS_DIR     (default: /opt/vecrm/builds)
#   VECRM_COMPOSE_DIR    (default: /opt/vecrm)
#   PREV_SESSION_TAG     (default: derived as 's<N-1>')
#   DRY_RUN=1            print steps without mutations
#   SKIP_REBUILD=1       skip the F-1 recreate (image load + retag only)

set -u

# --- Args ---
if [ "$#" -ne 2 ]; then
  echo "ERROR: usage: $0 <session-tag> <tarball-filename>" >&2
  echo "Example: $0 s20 vecrm-custom-s20-20260520T143000Z.tar.gz" >&2
  exit 2
fi
SESSION_TAG="$1"
TARBALL_NAME="$2"

# --- Config ---
VECRM_BUILDS_DIR="${VECRM_BUILDS_DIR:-/opt/vecrm/builds}"
VECRM_COMPOSE_DIR="${VECRM_COMPOSE_DIR:-/opt/vecrm}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_REBUILD="${SKIP_REBUILD:-0}"

SESSION_DIR="$VECRM_BUILDS_DIR/$SESSION_TAG"
TARBALL="$SESSION_DIR/$TARBALL_NAME"
CHECKSUM_FILE="${TARBALL}.sha256"
NEW_IMAGE_TAG="vecrm-custom:${SESSION_TAG}-mac-build"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEPLOY_LOG="$SESSION_DIR/deploy-${STAMP}.log"

# Derive previous session tag for rollback naming. Operator-overridable.
if [ -z "${PREV_SESSION_TAG:-}" ]; then
  # Strip leading 's' or 'S', decrement, prefix back. Fails gracefully.
  num="${SESSION_TAG#[sS]}"
  if [[ "$num" =~ ^[0-9]+$ ]]; then
    PREV_SESSION_TAG="s$((num - 1))"
  else
    PREV_SESSION_TAG="prev"
  fi
fi
ROLLBACK_TAG="vecrm-custom:${PREV_SESSION_TAG}-pre-${SESSION_TAG}-rollback"

bar() { printf '\n========== %s ==========\n' "$1" | tee -a "$DEPLOY_LOG"; }
log() { printf '%s\n' "$*" | tee -a "$DEPLOY_LOG"; }
run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf 'DRY-RUN: %s\n' "$*" | tee -a "$DEPLOY_LOG"
  else
    log "EXEC: $*"
    eval "$@" 2>&1 | tee -a "$DEPLOY_LOG"
    return "${PIPESTATUS[0]}"
  fi
}

mkdir -p "$SESSION_DIR"
: > "$DEPLOY_LOG"

bar "0. Preflight"
log "Session tag:       $SESSION_TAG"
log "Previous tag:      $PREV_SESSION_TAG"
log "Tarball:           $TARBALL"
log "Checksum file:     $CHECKSUM_FILE"
log "New image tag:     $NEW_IMAGE_TAG"
log "Rollback tag:      $ROLLBACK_TAG"
log "Compose dir:       $VECRM_COMPOSE_DIR"
log "Deploy log:        $DEPLOY_LOG"
log "DRY_RUN:           $DRY_RUN"
log "SKIP_REBUILD:      $SKIP_REBUILD"

# Tarball must exist
if [ ! -f "$TARBALL" ]; then
  log "ERROR: tarball not found at $TARBALL"
  exit 3
fi
# Checksum must exist
if [ ! -f "$CHECKSUM_FILE" ]; then
  log "ERROR: checksum file not found at $CHECKSUM_FILE"
  log "       Re-export from Mac with the rebuild script which produces .sha256 sidecar."
  exit 4
fi

bar "1. Verify tarball sha256"
EXPECTED_SHA="$(awk '{print $1}' "$CHECKSUM_FILE")"
log "Expected: $EXPECTED_SHA"
ACTUAL_SHA="$(sha256sum "$TARBALL" | awk '{print $1}')"
log "Actual:   $ACTUAL_SHA"
if [ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]; then
  log "ERROR: sha256 mismatch. Tarball corrupted or wrong file. Aborting."
  exit 5
fi
log "Tarball sha256 OK."

bar "2. Capture pre-deploy state (rollback inventory)"
log "Current images tagged vecrm-custom:"
docker images --no-trunc --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}' \
  | grep -E 'vecrm-custom|^REPOSITORY' | tee -a "$DEPLOY_LOG"

CURRENT_LATEST_SHA="$(docker images --no-trunc --format '{{.ID}}' vecrm-custom:latest | head -1)"
log "Current vecrm-custom:latest SHA: $CURRENT_LATEST_SHA"

CURRENT_RUNNING_SHA="$(docker inspect vecrm-backend-1 --format '{{.Image}}' 2>/dev/null)"
log "Current vecrm-backend-1 running image: $CURRENT_RUNNING_SHA"

bar "3. Preserve current :latest as rollback tag"
if [ -z "$CURRENT_LATEST_SHA" ]; then
  log "WARN: no current vecrm-custom:latest tag exists. Skipping rollback preservation."
elif docker image inspect "$ROLLBACK_TAG" >/dev/null 2>&1; then
  log "Rollback tag $ROLLBACK_TAG already exists — leaving it alone (likely a re-run)."
else
  run "docker tag '$CURRENT_LATEST_SHA' '$ROLLBACK_TAG'"
  log "Tagged current :latest as $ROLLBACK_TAG"
fi

bar "4. Load new image from tarball"
log "This may take 30-60 seconds for an 800+ MB tarball."
run "gunzip -c '$TARBALL' | docker load"

# Verify new image landed
NEW_IMAGE_SHA="$(docker images --no-trunc --format '{{.ID}}' "$NEW_IMAGE_TAG" | head -1)"
if [ -z "$NEW_IMAGE_SHA" ]; then
  log "ERROR: image $NEW_IMAGE_TAG not found after docker load. Tarball may not contain expected tag."
  log "Available vecrm-custom images:"
  docker images --no-trunc --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}' | grep vecrm-custom | tee -a "$DEPLOY_LOG"
  exit 6
fi
log "New image loaded: $NEW_IMAGE_TAG"
log "New image SHA:    $NEW_IMAGE_SHA"

bar "5. Retag new image as :latest"
run "docker tag '$NEW_IMAGE_TAG' vecrm-custom:latest"
log "Retagged $NEW_IMAGE_TAG as vecrm-custom:latest"

if [ "$SKIP_REBUILD" = "1" ]; then
  bar "SKIP_REBUILD=1 — stopping before F-1 recreate"
  log "Image loaded and retagged. F-1 recreate skipped per SKIP_REBUILD=1."
  log "To complete: run with SKIP_REBUILD=0 or manually run the F-2/F-1 sequence below."
  exit 0
fi

bar "6. F-2 lock: FLUSHALL vecrm-redis-cache-1 BEFORE recreate"
# Read pre-flush key count for log
PRE_FLUSH_KEYS="$(docker exec vecrm-redis-cache-1 redis-cli dbsize 2>/dev/null | awk '{print $1}')"
log "Pre-flush key count: ${PRE_FLUSH_KEYS:-unknown}"
run "docker exec vecrm-redis-cache-1 redis-cli FLUSHALL"
POST_FLUSH_KEYS="$(docker exec vecrm-redis-cache-1 redis-cli dbsize 2>/dev/null | awk '{print $1}')"
log "Post-flush key count: ${POST_FLUSH_KEYS:-unknown}"

bar "7. F-1 lock: coherent recreate via 4-f override chain --no-build"
cd "$VECRM_COMPOSE_DIR" || { log "ERROR: cannot cd to $VECRM_COMPOSE_DIR"; exit 7; }
F1_CMD="docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.noproxy.yaml \
  up -d --no-build --force-recreate"
log "Recreate command:"
log "  $F1_CMD"
run "$F1_CMD"

bar "8. Post-deploy fleet check"
sleep 5  # give containers a moment to settle
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'vecrm-' | tee -a "$DEPLOY_LOG"
VECRM_RUNNING="$(docker ps --filter 'name=vecrm-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
log "vecrm containers running: $VECRM_RUNNING (expected: 9)"
if [ "$VECRM_RUNNING" -lt 9 ]; then
  log "WARN: fewer than 9 vecrm containers running. Investigate before declaring success."
fi

bar "9. Post-deploy dual-200 check"
ROOT_STATUS="$(curl -sk -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/ 2>/dev/null || echo 000)"
log "Root URL status: $ROOT_STATUS (expected: 200)"
# Hashed asset probe — we discover the asset path from the running frontend.
HASHED_ASSET="$(docker exec vecrm-frontend-1 sh -c 'ls /usr/share/nginx/html/assets/*.js 2>/dev/null | head -1' 2>/dev/null)"
if [ -n "$HASHED_ASSET" ]; then
  ASSET_PATH="${HASHED_ASSET#/usr/share/nginx/html}"
  ASSET_STATUS="$(curl -sk -o /dev/null -w '%{http_code}' "http://127.0.0.1:8091${ASSET_PATH}" 2>/dev/null || echo 000)"
  log "Hashed asset $ASSET_PATH: $ASSET_STATUS (expected: 200)"
else
  log "WARN: could not locate hashed asset to probe — dual-200 check incomplete."
fi

bar "10. VECRM-L8 dual-surface allocator verification"
ALLOCATOR_PATH="/home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py"
CONTAINER_SHA="$(docker exec vecrm-backend-1 sha256sum "$ALLOCATOR_PATH" 2>/dev/null | awk '{print $1}')"
log "Allocator sha256 inside vecrm-backend-1: $CONTAINER_SHA"
# Git side — uses VPS clone at /opt/vecrm/vecrm-src
GIT_ALLOCATOR="/opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py"
if [ -f "$GIT_ALLOCATOR" ]; then
  GIT_SHA="$(sha256sum "$GIT_ALLOCATOR" | awk '{print $1}')"
  log "Allocator sha256 in git clone:             $GIT_SHA"
  if [ "$CONTAINER_SHA" = "$GIT_SHA" ]; then
    log "VECRM-L8 dual-surface: PASS (match)"
  else
    log "VECRM-L8 dual-surface: FAIL — git and container disagree. Investigate."
  fi
else
  log "WARN: $GIT_ALLOCATOR not found — cannot verify VECRM-L8 dual-surface"
fi

bar "DONE"
log "Deploy log: $DEPLOY_LOG"
log
log "Final image inventory:"
docker images --no-trunc --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}' | grep vecrm-custom | tee -a "$DEPLOY_LOG"
log
log "If anything above looks wrong, rollback with:"
log "  docker tag $ROLLBACK_TAG vecrm-custom:latest"
log "  $F1_CMD"
