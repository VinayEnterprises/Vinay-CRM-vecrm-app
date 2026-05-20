#!/usr/bin/env bash
# vecrm-build.sh — VPS-side vecrm image rebuild
# Canonical per VECRM-S20-A (revised S21)
# Run on VPS in /opt/vecrm/. Operator-runs-on-VPS, NOT Mac.

set -euo pipefail

SESSION_TAG="${1:-}"
if [ -z "${SESSION_TAG}" ]; then
  echo "Usage: $0 <session-tag>"
  echo "  e.g.  $0 s21-fix-staging"
  exit 1
fi

REPO=/opt/vecrm
SRC=${REPO}/vecrm-src
LOG="${REPO}/build-${SESSION_TAG}-$(date -u +%Y%m%dT%H%M%SZ).log"

cd "${REPO}"

echo "=== vecrm-build.sh — session tag: ${SESSION_TAG} ==="
echo ""

echo "--- 1. Pre-build state ---"
echo "vecrm-src HEAD: $(git -C ${SRC} rev-parse HEAD)"
echo "vecrm-src remote ref: $(git -C ${SRC} rev-parse origin/main 2>/dev/null || echo '(no origin/main)')"
echo "Current vecrm-custom:latest: $(docker images vecrm-custom:latest --format '{{.ID}}' | head -1)"
echo "Free RAM: $(free -h | awk '/^Mem:/ {print $7}') available"
echo ""

read -p "Proceed with build? Tag will be vecrm-custom:${SESSION_TAG} + :latest. [y/N] " confirm
if [ "${confirm}" != "y" ]; then
  echo "Aborted."
  exit 1
fi

echo ""
echo "--- 2. Build (nohup-detached, log: ${LOG}) ---"
nohup docker build --no-cache \
  --build-arg=FRAPPE_BRANCH=v16.18.2 \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --secret=id=apps_json,src=/opt/vecrm/apps.json \
  --file=/opt/vecrm/images/custom/Containerfile \
  --tag=vecrm-custom:${SESSION_TAG} \
  --tag=vecrm-custom:latest \
  /opt/vecrm > "${LOG}" 2>&1 &

BUILD_PID=$!
echo "Build started, PID: ${BUILD_PID}"
echo "Tail log: tail -f ${LOG}"
echo ""

echo "--- 3. Polling (60s intervals) ---"
while kill -0 ${BUILD_PID} 2>/dev/null; do
  sleep 60
  echo "  $(date -u +%H:%M:%S) — build still running"
done

wait ${BUILD_PID}
BUILD_EXIT=$?

echo ""
echo "--- 4. Build complete (exit: ${BUILD_EXIT}) ---"
if [ "${BUILD_EXIT}" -ne 0 ]; then
  echo "BUILD FAILED. See ${LOG}."
  exit ${BUILD_EXIT}
fi

NEW_SHA=$(docker images vecrm-custom:${SESSION_TAG} --no-trunc --format '{{.ID}}' | head -1)
echo "New image SHA: ${NEW_SHA}"
echo ""
echo "VECRM_FETCH_GATE and VECRM_POSTINSTALL_GATE both PASS (build would have failed otherwise)."
echo ""
echo "Next: bash vecrm-deploy.sh ${SESSION_TAG} s<N>-pre-fix-rollback"
