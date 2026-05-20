#!/usr/bin/env bash
# vecrm-rebuild-pathB.sh — Mac amd64 buildx rebuild (Path B)
#
# Runs on macOS (Apple Silicon or Intel). Builds a linux/amd64 vecrm image
# from the GitHub repo at ~/GitHub/vecrm, exports as gzipped tarball, and
# stages for scp to the VPS.
#
# Locks honored:
#   VECRM-S19-A — verify remote ref after fetch
#   VECRM-S19-B — positively verify apps.json manifest before build
#   VECRM-S19-E — derive build context "minimum set" from every COPY/ADD
#   VECRM-S20-A — Path B is the permanent rebuild path
#
# Usage:
#   ./vecrm-rebuild-pathB.sh <session-tag>
# Example:
#   ./vecrm-rebuild-pathB.sh s20
#
# Environment overrides:
#   VECRM_REPO         (default: ~/Documents/GitHub/vecrm)
#   VECRM_BUILD_CTX    (default: ~/vecrm-build)
#   VECRM_OUT_DIR      (default: ~/vecrm-build/dist)
#   SKIP_FETCH=1       skip the git fetch+reset step (use whatever HEAD is there)
#   DRY_RUN=1          print steps without executing buildx or tarball export

set -u  # we manage errors explicitly per step

# --- Args ---
if [ "$#" -ne 1 ]; then
  echo "ERROR: session-tag required. Usage: $0 <session-tag>" >&2
  echo "Example: $0 s20" >&2
  exit 2
fi
SESSION_TAG="$1"

# --- Config ---
VECRM_REPO="${VECRM_REPO:-$HOME/Documents/GitHub/vecrm}"
VECRM_BUILD_CTX="${VECRM_BUILD_CTX:-$HOME/vecrm-build}"
VECRM_OUT_DIR="${VECRM_OUT_DIR:-$VECRM_BUILD_CTX/dist}"
DRY_RUN="${DRY_RUN:-0}"
SKIP_FETCH="${SKIP_FETCH:-0}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
IMAGE_TAG="vecrm-custom:${SESSION_TAG}-mac-build"
TARBALL="${VECRM_OUT_DIR}/vecrm-custom-${SESSION_TAG}-${STAMP}.tar.gz"

bar() { printf '\n========== %s ==========\n' "$1"; }
run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf 'DRY-RUN: %s\n' "$*"
  else
    eval "$@"
  fi
}

# --- Preflight ---
bar "0. Preflight"
echo "Session tag:       $SESSION_TAG"
echo "Repo:              $VECRM_REPO"
echo "Build context:     $VECRM_BUILD_CTX"
echo "Output dir:        $VECRM_OUT_DIR"
echo "Image tag:         $IMAGE_TAG"
echo "Tarball will be:   $TARBALL"
echo "DRY_RUN:           $DRY_RUN"
echo "SKIP_FETCH:        $SKIP_FETCH"
echo

# Tool checks
for tool in docker git tar shasum scp; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: required tool not found: $tool" >&2
    exit 3
  fi
done

# Repo must exist
if [ ! -d "$VECRM_REPO/.git" ]; then
  echo "ERROR: $VECRM_REPO is not a git repo" >&2
  exit 4
fi

# Docker buildx must be available
if ! docker buildx version >/dev/null 2>&1; then
  echo "ERROR: docker buildx not available — install Docker Desktop or buildx plugin" >&2
  exit 5
fi

# --- Step 1: align Mac local main with origin/main (VECRM-S19-A) ---
bar "1. Align repo with origin/main"
if [ "$SKIP_FETCH" = "1" ]; then
  echo "SKIP_FETCH=1 — using whatever HEAD is currently checked out"
  HEAD_SHA="$(git -C "$VECRM_REPO" rev-parse HEAD)"
  echo "Current HEAD: $HEAD_SHA"
else
  run "git -C '$VECRM_REPO' fetch origin"
  # VECRM-S19-A: assert remote-tracking ref exists before relying on it
  if ! git -C "$VECRM_REPO" rev-parse --verify origin/main >/dev/null 2>&1; then
    echo "ERROR: origin/main ref does not exist after fetch. Check remote refspec." >&2
    exit 6
  fi
  REMOTE_SHA="$(git -C "$VECRM_REPO" rev-parse origin/main)"
  echo "origin/main = $REMOTE_SHA"
  run "git -C '$VECRM_REPO' checkout main"
  run "git -C '$VECRM_REPO' reset --hard origin/main"
  HEAD_SHA="$(git -C "$VECRM_REPO" rev-parse HEAD)"
  if [ "$HEAD_SHA" != "$REMOTE_SHA" ]; then
    echo "ERROR: HEAD ($HEAD_SHA) does not match origin/main ($REMOTE_SHA) after reset" >&2
    exit 7
  fi
  echo "Local HEAD now aligned: $HEAD_SHA"
fi

# --- Step 2: build context minimum set audit (VECRM-S19-E) ---
bar "2. Build context — minimum set from Containerfile COPY/ADD"
CONTAINERFILE="$VECRM_REPO/images/custom/Containerfile"
if [ ! -f "$CONTAINERFILE" ]; then
  echo "ERROR: Containerfile not found at $CONTAINERFILE" >&2
  echo "Path B baseline assumes images/custom/Containerfile — investigate before proceeding." >&2
  exit 8
fi
echo "Containerfile: $CONTAINERFILE"
echo
echo "COPY/ADD directives in Containerfile (these define the minimum set):"
grep -nE '^\s*(COPY|ADD)\s+' "$CONTAINERFILE" | sed 's/^/  /'
echo
echo "Required paths derived from above (relative to build context root):"
REQUIRED_PATHS="$(grep -E '^\s*(COPY|ADD)\s+' "$CONTAINERFILE" \
  | awk '{
      # strip leading COPY/ADD and any --flag=value tokens; collect SRCs (all but last token)
      $1=""
      for (i=2; i<NF; i++) {
        if ($i ~ /^--/) continue
        print $i
      }
    }' | sort -u)"
echo "$REQUIRED_PATHS" | sed 's/^/  /'
echo
echo "VECRM-S19-E: verify each path exists in the build context after staging (step 3)."

# --- Step 3: stage build context ---
bar "3. Stage build context at $VECRM_BUILD_CTX"
run "mkdir -p '$VECRM_BUILD_CTX' '$VECRM_OUT_DIR'"
# Copy the repo contents into the build context. We use rsync to handle re-runs.
# Excluding .git keeps the context lean; the build doesn't need history.
if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync required for build context staging" >&2
  exit 9
fi
run "rsync -a --delete --exclude='.git' --exclude='dist/' '$VECRM_REPO/' '$VECRM_BUILD_CTX/'"
echo "Build context staged. Verifying required paths:"
MISSING_PATHS=0
while IFS= read -r p; do
  [ -z "$p" ] && continue
  # Strip trailing slash for existence test
  test_p="${p%/}"
  if [ ! -e "$VECRM_BUILD_CTX/$test_p" ]; then
    echo "  MISSING: $test_p" >&2
    MISSING_PATHS=$((MISSING_PATHS + 1))
  else
    echo "  ok:      $test_p"
  fi
done <<< "$REQUIRED_PATHS"

if [ "$MISSING_PATHS" -gt 0 ]; then
  echo
  echo "ERROR: $MISSING_PATHS required path(s) missing from build context. Cannot proceed." >&2
  echo "VECRM-S19-E says: do NOT infer minimum set from directory inspection." >&2
  echo "If a required path is missing, the repo itself is incomplete — investigate." >&2
  exit 10
fi

# --- Step 4: apps.json manifest verification (VECRM-S19-B) ---
bar "4. apps.json manifest check"
APPS_JSON="$VECRM_BUILD_CTX/apps.json"
if [ ! -f "$APPS_JSON" ]; then
  echo "ERROR: apps.json not found in build context" >&2
  exit 11
fi
echo "apps.json contents:"
cat "$APPS_JSON" | sed 's/^/  /'
echo
# Positive verification per VECRM-S19-B: assert known-required apps are referenced.
REQUIRED_APPS="frappe vecrm"
for app in $REQUIRED_APPS; do
  if grep -q "\"$app\"" "$APPS_JSON" || grep -qE "/${app}\\.git" "$APPS_JSON" || grep -qE "/${app}(\"|/)" "$APPS_JSON"; then
    echo "  apps.json references: $app  ✓"
  else
    echo "  apps.json MISSING reference to: $app  ✗" >&2
    echo "ERROR: manifest does not reference required app $app" >&2
    exit 12
  fi
done

# --- Step 5: build ---
bar "5. docker buildx build (linux/amd64, --no-cache, --load)"
echo "This step takes ~5 minutes. Vite is the long pole (~3.5 min)."
echo
BUILD_CMD="docker buildx build \
  --no-cache \
  --platform linux/amd64 \
  --secret=id=apps_json,src='$VECRM_BUILD_CTX/apps.json' \
  --file='$CONTAINERFILE' \
  --tag='$IMAGE_TAG' \
  --load \
  '$VECRM_BUILD_CTX'"
echo "Command:"
echo "  $BUILD_CMD"
echo
run "$BUILD_CMD"

if [ "$DRY_RUN" != "1" ]; then
  # Verify image landed
  IMAGE_SHA="$(docker images --no-trunc --format '{{.ID}}' "$IMAGE_TAG" | head -1)"
  if [ -z "$IMAGE_SHA" ]; then
    echo "ERROR: image $IMAGE_TAG not found after build" >&2
    exit 13
  fi
  echo "Image built: $IMAGE_TAG"
  echo "Image SHA:   $IMAGE_SHA"
fi

# --- Step 6: export to gzipped tarball ---
bar "6. Export image to gzipped tarball"
echo "Tarball:  $TARBALL"
run "docker save '$IMAGE_TAG' | gzip > '$TARBALL'"

if [ "$DRY_RUN" != "1" ]; then
  TARBALL_SIZE="$(stat -f %z "$TARBALL" 2>/dev/null || stat -c %s "$TARBALL")"
  TARBALL_SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
  echo "Tarball size: $TARBALL_SIZE bytes (~$((TARBALL_SIZE / 1024 / 1024)) MB)"
  echo "Tarball sha256:"
  echo "  $TARBALL_SHA"

  # Stash sha256 alongside tarball for the VPS-side script to verify against
  echo "$TARBALL_SHA  $(basename "$TARBALL")" > "${TARBALL}.sha256"
  echo "Saved checksum: ${TARBALL}.sha256"
fi

# --- Step 7: print scp instructions ---
bar "7. Next steps (manual)"
echo "Mac-side rebuild complete. To deploy on the VPS:"
echo
echo "  scp '$TARBALL' '${TARBALL}.sha256' root@217.216.58.117:/opt/vecrm/builds/${SESSION_TAG}/"
echo "  ssh root@217.216.58.117 'bash /opt/vecrm/builds/${SESSION_TAG}/vecrm-deploy-image.sh ${SESSION_TAG} $(basename "$TARBALL")'"
echo
echo "Before scp, ensure VPS staging dir exists:"
echo "  ssh root@217.216.58.117 'mkdir -p /opt/vecrm/builds/${SESSION_TAG}/'"
echo
echo "Then scp the vecrm-deploy-image.sh script itself if not already on the VPS."
echo

bar "DONE"
echo "Session tag:    $SESSION_TAG"
echo "HEAD built:     $HEAD_SHA"
echo "Image tag:      $IMAGE_TAG"
echo "Tarball:        $TARBALL"
[ "$DRY_RUN" != "1" ] && echo "Tarball sha256: $TARBALL_SHA"
echo
echo "If this output looks wrong, do NOT scp to VPS. Investigate first."
