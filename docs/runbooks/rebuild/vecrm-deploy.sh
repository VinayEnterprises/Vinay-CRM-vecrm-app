#!/usr/bin/env bash
# vecrm-deploy.sh — VPS-side deploy of new vecrm-custom image
# Canonical per VECRM-S20-A (revised S21). F-1/F-2 coherent recreate.
# Run on VPS in /opt/vecrm/. Operator-runs-on-VPS.

set -euo pipefail

NEW_TAG="${1:-}"
ROLLBACK_TAG="${2:-}"

if [ -z "${NEW_TAG}" ] || [ -z "${ROLLBACK_TAG}" ]; then
  echo "Usage: $0 <new-image-tag> <rollback-tag>"
  echo "  e.g.  $0 s21-fix-staging s21-pre-fix-rollback"
  exit 1
fi

REPO=/opt/vecrm
cd "${REPO}"

echo "=== vecrm-deploy.sh — new=${NEW_TAG} rollback=${ROLLBACK_TAG} ==="
echo ""

echo "--- 1. Pre-deploy state ---"
CURRENT_LATEST_SHA=$(docker images vecrm-custom:latest --no-trunc --format '{{.ID}}' | head -1)
NEW_SHA=$(docker images vecrm-custom:${NEW_TAG} --no-trunc --format '{{.ID}}' | head -1)
echo "Current :latest:    ${CURRENT_LATEST_SHA}"
echo "Incoming ${NEW_TAG}: ${NEW_SHA}"
if [ -z "${NEW_SHA}" ]; then
  echo "ERROR: vecrm-custom:${NEW_TAG} does not exist. Build first."
  exit 1
fi
echo ""

read -p "Proceed with deploy? Preserves :latest as :${ROLLBACK_TAG}, retags ${NEW_TAG}->:latest, recreates fleet. [y/N] " confirm
if [ "${confirm}" != "y" ]; then
  echo "Aborted."
  exit 1
fi

echo ""
echo "--- 2. Preserve current :latest as :${ROLLBACK_TAG} ---"
docker tag ${CURRENT_LATEST_SHA} vecrm-custom:${ROLLBACK_TAG}

echo ""
echo "--- 3. Retag ${NEW_TAG} as :latest ---"
docker tag vecrm-custom:${NEW_TAG} vecrm-custom:latest

echo ""
echo "--- 4. F-2: FLUSHALL vecrm-redis-cache-1 ---"
docker exec vecrm-redis-cache-1 redis-cli FLUSHALL

echo ""
echo "--- 5. F-1: 4-f override chain --no-build --force-recreate ---"
docker compose \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.noproxy.yaml \
  up -d --no-build --force-recreate

echo ""
echo "--- 6. Verify fleet on new image ---"
sleep 5
RUNNING_NEW=$(docker ps --filter "ancestor=vecrm-custom:latest" --format "{{.Names}}" | wc -l | tr -d ' ')
echo "Containers running new :latest: ${RUNNING_NEW}/9 expected"

echo ""
echo "--- 7. Verify VECRM-L8 dual-surface ---"
HOST_SHA=$(sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py | awk '{print $1}')
CONTAINER_SHA=$(docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py | awk '{print $1}')
echo "Host:      ${HOST_SHA}"
echo "Container: ${CONTAINER_SHA}"
if [ "${HOST_SHA}" = "${CONTAINER_SHA}" ]; then
  echo "VECRM-L8: PASS (dual-surface match)"
else
  echo "VECRM-L8: FAIL — surfaces diverged. INVESTIGATE before declaring deploy complete."
fi

echo ""
echo "Deploy complete. Run cold-check or smoke test before declaring gate closed."
