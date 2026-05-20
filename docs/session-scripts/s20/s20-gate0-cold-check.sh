#!/usr/bin/env bash
# VECRM S20 Gate 0 — Cold-check
# Read-only verification of seven assertions banked at S19 close.
# No state mutations. Safe to run any number of times.
#
# Expected runtime: < 15 seconds.
# Pass criteria: every line below stamped "EXPECT: ..." matches the printed value.

set -u  # do NOT set -e — we want every check to run even if one fails

# --- Config (S19-close-handover §2, ground truth) ---
EXPECT_VECRM_SHA="47e26dad4c245632c3f17b0674721ef595800b43"
EXPECT_IMAGE_SHA="sha256:6656988b378599ed12f44463e6863e349aa186f9b2def9776d9d4f2d796b59fa"
EXPECT_VECRM_FLEET=9
EXPECT_VEMIO_FLEET=18
SITE_DB="_02c50791cf17d9de"

# Edit this path if your vecrm checkout lives elsewhere on the VPS.
VECRM_REPO="${VECRM_REPO:-/opt/vecrm/vecrm-src}"

bar() { printf '\n========== %s ==========\n' "$1"; }

bar "1. vecrm origin/main HEAD"
echo "EXPECT: $EXPECT_VECRM_SHA"
ACTUAL_VECRM_SHA="$(git -C "$VECRM_REPO" rev-parse origin/main 2>&1 || true)"
echo "ACTUAL: $ACTUAL_VECRM_SHA"

bar "2. Running vecrm-backend-1 image SHA"
echo "EXPECT: $EXPECT_IMAGE_SHA"
ACTUAL_IMAGE_SHA="$(docker inspect vecrm-backend-1 --format '{{.Image}}' 2>&1 || true)"
echo "ACTUAL: $ACTUAL_IMAGE_SHA"

bar "3. Allocator voucher_counter.py — dual-surface SHA"
echo "Looking for sha 7ad2b3a3… (S19-close §2)"
echo
echo "--- Surface 1: git (source of truth) ---"
# voucher_counter.py path is inside the vecrm app folder under apps/vecrm
# We probe candidates rather than hard-coding to avoid the prose-vs-source pitfall.
GIT_CANDIDATES="$(git -C "$VECRM_REPO" ls-files 2>/dev/null | grep -i 'voucher_counter\.py$' || true)"
echo "Candidate paths in repo:"
echo "$GIT_CANDIDATES"
if [ -n "$GIT_CANDIDATES" ]; then
  while IFS= read -r p; do
    [ -z "$p" ] && continue
    GIT_SHA="$(git -C "$VECRM_REPO" hash-object "$p" 2>/dev/null || true)"
    echo "  $p -> git hash-object: $GIT_SHA"
  done <<< "$GIT_CANDIDATES"
fi
echo
echo "--- Surface 2: running container (inside vecrm-backend-1) ---"
# Locate the file inside the container and sha256 it; we use find rather than
# guessing the bench-rendered path.
docker exec vecrm-backend-1 bash -lc '
  set -u
  paths="$(find / -type f -name voucher_counter.py 2>/dev/null | grep -v /proc/ || true)"
  if [ -z "$paths" ]; then
    echo "  (no voucher_counter.py found inside container)"
  else
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      sha="$(sha256sum "$p" | awk "{print \$1}")"
      echo "  $p  sha256: $sha"
    done <<< "$paths"
  fi
' 2>&1 || true

bar "4. Fleet headcount"
VECRM_RUNNING="$(docker ps --filter 'name=vecrm-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
VEMIO_RUNNING="$(docker ps --filter 'name=vemio-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
HELPDESK_RUNNING="$(docker ps --filter 'name=helpdesk' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
echo "vecrm    EXPECT: $EXPECT_VECRM_FLEET   ACTUAL: $VECRM_RUNNING"
echo "vemio    EXPECT: $EXPECT_VEMIO_FLEET   ACTUAL: $VEMIO_RUNNING"
echo "helpdesk EXPECT: >=1 healthy           ACTUAL containers running: $HELPDESK_RUNNING"
echo
echo "Health states (any 'unhealthy' below is a flag):"
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'vecrm-|vemio-|helpdesk' || true

bar "5. Voucher counters LEAD-26-27 and INQ-26-27"
echo "EXPECT both: last_value = 0"
printf '%s\n' "SELECT name, last_value FROM \`tabVECRM Voucher Counter\` WHERE name IN ('LEAD-26-27','INQ-26-27');" \
  | docker exec -i vecrm-db-1 bash -lc "MYSQL_PWD=\$(cat /run/secrets/db_root_password 2>/dev/null || echo \"\$MYSQL_ROOT_PASSWORD\") mariadb -uroot $SITE_DB" 2>&1 || true

bar "6. Three test tables row counts"
echo "EXPECT all three: 0 rows"
printf '%s\n' \
  "SELECT 'tabVECRM Lead' AS tbl, COUNT(*) AS rows_ FROM \`tabVECRM Lead\`
   UNION ALL SELECT 'tabVECRM Inquiry', COUNT(*) FROM \`tabVECRM Inquiry\`
   UNION ALL SELECT 'tabVECRM Inquiry Audit Log', COUNT(*) FROM \`tabVECRM Inquiry Audit Log\`;" \
  | docker exec -i vecrm-db-1 bash -lc "MYSQL_PWD=\$(cat /run/secrets/db_root_password 2>/dev/null || echo \"\$MYSQL_ROOT_PASSWORD\") mariadb -uroot $SITE_DB" 2>&1 || true

bar "7. S18 rollback image presence"
echo "EXPECT: vecrm-custom:s18-pre-s19-rollback exists with sha256:3fea7d28…"
docker images --no-trunc --format 'table {{.Repository}}:{{.Tag}}\t{{.ID}}' \
  | grep -E 'vecrm-custom|^REPOSITORY' || true

bar "DONE"
echo "Adjudication criteria (set BEFORE results, per operating model):"
echo "  1. vecrm SHA      == $EXPECT_VECRM_SHA                                       -> PASS/FAIL"
echo "  2. image SHA      == $EXPECT_IMAGE_SHA                                       -> PASS/FAIL"
echo "  3. allocator      git hash-object matches sha inside container (prefix 7ad2b3a3) -> PASS/FAIL"
echo "  4. fleet          vecrm=9, vemio=18, helpdesk healthy                            -> PASS/FAIL"
echo "  5. counters       LEAD-26-27=0 AND INQ-26-27=0                                   -> PASS/FAIL"
echo "  6. test tables    all three = 0 rows                                             -> PASS/FAIL"
echo "  7. rollback image vecrm-custom:s18-pre-s19-rollback present with sha 3fea7d28    -> PASS/FAIL"
echo
echo "Any FAIL -> stop, surface, do NOT proceed to A."
