#!/usr/bin/env bash
# vps-prune.sh — VECRM VPS image prune policy
#
# Purpose
# -------
# Reclaim disk space by pruning old `vecrm-custom` rollback tags on the VPS.
# Keeps the latest 3 session-tagged rollback images by session number;
# everything else matching the `sNN-pre-*-rollback` pattern is candidate
# for pruning. Also clears Docker builder cache.
#
# Policy
# ------
# - Keep:    `vecrm-custom:latest`                   (always)
# - Keep:    `vecrm-custom:sNN-pre-*-rollback`       (top 3 by NN)
# - Prune:   `vecrm-custom:sNN-pre-*-rollback`       (everything older)
# - Ignore:  any tag NOT matching `sNN-pre-*-rollback` (untouched)
# - Plus:    `docker builder prune -a -f`            (always, in --execute)
#
# Usage
# -----
#   ./vps-prune.sh               # dry-run; prints what WOULD be pruned
#   ./vps-prune.sh --execute     # actually prune
#
# Exit codes
# ----------
#   0  success (or nothing to prune in dry-run)
#   1  docker command failure
#   2  nothing to prune (when --execute and zero targets identified)
#
# When to run
# -----------
# Run before any `docker compose build --no-cache <service>` deploy that may
# create disk pressure. S33 hit "no space left on device" mid-deploy and
# required a 3-tranche recovery (~58GB freed). This script codifies the
# prune so the next deploy starts clean.
#
# Optional cron (NOT installed by this script; install manually if desired):
#   # weekly Sunday 03:00 IST auto-prune in --execute mode
#   0 3 * * 0 /root/scripts/vps-prune.sh --execute >> /var/log/vps-prune.log 2>&1
#
# Origin: PD-S33-NEXT-IMAGE-PRUNE — VECRM S34

set -euo pipefail

EXECUTE=0
if [[ "${1:-}" == "--execute" ]]; then
    EXECUTE=1
fi

REPO="vecrm-custom"
KEEP_COUNT=3

echo "=== vps-prune.sh ==="
if [[ $EXECUTE -eq 1 ]]; then
    echo "Mode: EXECUTE (will actually prune)"
else
    echo "Mode: DRY-RUN (no changes — pass --execute to prune)"
fi
echo "Repo: $REPO"
echo "Keep latest: $KEEP_COUNT session-tagged rollback images"
echo ""

# Collect all matching rollback tags + their session numbers
# Tag format: sNN-pre-*-rollback (e.g. s33-pre-pr-followup-phase-1-rollback)
mapfile -t ALL_TAGS < <(
    docker images "$REPO" --format '{{.Tag}}' \
    | grep -E '^s[0-9]+-pre-.*-rollback$' \
    | sort -u
)

if [[ ${#ALL_TAGS[@]} -eq 0 ]]; then
    echo "No matching rollback tags found. Nothing to do."
    # Still run builder prune in execute mode (independent of tag prune)
    if [[ $EXECUTE -eq 1 ]]; then
        echo ""
        echo "Running: docker builder prune -a -f"
        docker builder prune -a -f
    fi
    exit 0
fi

echo "Found ${#ALL_TAGS[@]} session-tagged rollback images:"
printf '  %s\n' "${ALL_TAGS[@]}"
echo ""

# Sort by session number descending (highest first), pick first KEEP_COUNT
mapfile -t KEEP_TAGS < <(
    printf '%s\n' "${ALL_TAGS[@]}" \
    | awk -F'-' '{
        sess=$1; sub(/^s/,"",sess);
        printf "%05d %s\n", sess, $0
      }' \
    | sort -rn \
    | head -n "$KEEP_COUNT" \
    | awk '{print $2}'
)

# Targets to prune = ALL_TAGS minus KEEP_TAGS
mapfile -t PRUNE_TAGS < <(
    comm -23 \
        <(printf '%s\n' "${ALL_TAGS[@]}" | sort) \
        <(printf '%s\n' "${KEEP_TAGS[@]}" | sort)
)

echo "KEEP (latest $KEEP_COUNT):"
printf '  %s\n' "${KEEP_TAGS[@]}"
echo ""

if [[ ${#PRUNE_TAGS[@]} -eq 0 ]]; then
    echo "No images to prune (have ${#ALL_TAGS[@]}, keeping $KEEP_COUNT)."
    if [[ $EXECUTE -eq 1 ]]; then
        echo ""
        echo "Running: docker builder prune -a -f"
        docker builder prune -a -f
        exit 0
    fi
    exit 0
fi

echo "PRUNE candidates (${#PRUNE_TAGS[@]}):"
for tag in "${PRUNE_TAGS[@]}"; do
    SIZE=$(docker images "$REPO:$tag" --format '{{.Size}}' | head -1)
    printf '  %s:%s  (%s)\n' "$REPO" "$tag" "$SIZE"
done
echo ""

if [[ $EXECUTE -eq 0 ]]; then
    echo "Dry-run complete. Re-run with --execute to actually prune."
    exit 0
fi

# EXECUTE path
echo "=== Executing prune ==="
FAIL=0
for tag in "${PRUNE_TAGS[@]}"; do
    echo "Removing $REPO:$tag ..."
    if docker rmi "$REPO:$tag"; then
        echo "  ✓ removed"
    else
        echo "  ✗ FAILED (may be in use or already gone)"
        FAIL=1
    fi
done

echo ""
echo "Running: docker builder prune -a -f"
docker builder prune -a -f

echo ""
echo "=== Disk after prune ==="
df -h / | grep -v Filesystem

if [[ $FAIL -ne 0 ]]; then
    exit 1
fi
exit 0
