#!/usr/bin/env bash
# VECRM S20 Gate 7 — Post-upgrade verification
# Reads the Gate 2 baseline.kv file and diffs every captured field against
# current post-upgrade state. Adjudicates each field against pre-stated
# criteria (changed-expected vs changed-unexpected vs unchanged).
#
# Pure observation. No mutations. Safe to re-run any number of times.
#
# Usage:
#   ./s20-gate7-post-upgrade-verify.sh
# Optional:
#   BASELINE_DIR=/opt/vecrm/.s20_pre_upgrade_snapshot_<stamp>/  override if multiple snapshots present

set -u

# --- Locate the baseline ---
# Find the most recent pre-upgrade snapshot directory.
if [ -n "${BASELINE_DIR:-}" ]; then
  SNAPSHOT_DIR="$BASELINE_DIR"
else
  SNAPSHOT_DIR="$(ls -1dt /opt/vecrm/.s20_pre_upgrade_snapshot_* 2>/dev/null | head -1)"
fi

if [ -z "$SNAPSHOT_DIR" ] || [ ! -d "$SNAPSHOT_DIR" ]; then
  echo "ERROR: cannot locate Gate 2 baseline snapshot directory" >&2
  echo "Expected: /opt/vecrm/.s20_pre_upgrade_snapshot_<stamp>/" >&2
  exit 2
fi

BASELINE="$SNAPSHOT_DIR/baseline.kv"
if [ ! -f "$BASELINE" ]; then
  echo "ERROR: baseline.kv not found in $SNAPSHOT_DIR" >&2
  exit 3
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_LOG="/opt/vecrm/.s20_gate7_verify_${STAMP}.log"

# --- Helpers ---
bar() { printf '\n========== %s ==========\n' "$1" | tee -a "$OUT_LOG"; }
log() { printf '%s\n' "$*" | tee -a "$OUT_LOG"; }

# Read a key from baseline.kv (key=value lines)
baseline_get() {
  local key="$1"
  awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/, ""); print; exit}' "$BASELINE"
}

# Adjudicate: print PASS/FAIL/CHANGE with expected vs actual
# Args: label, expected, actual, expected-change ("same"|"change"|"increase")
adj() {
  local label="$1" expected="$2" actual="$3" mode="$4"
  case "$mode" in
    same)
      if [ "$expected" = "$actual" ]; then
        printf '  %-30s PASS    (unchanged: %s)\n' "$label" "$actual" | tee -a "$OUT_LOG"
      else
        printf '  %-30s FAIL    (expected unchanged: was %s, now %s)\n' "$label" "$expected" "$actual" | tee -a "$OUT_LOG"
      fi
      ;;
    change)
      if [ "$expected" = "$actual" ]; then
        printf '  %-30s WARN    (expected to CHANGE but unchanged: %s)\n' "$label" "$actual" | tee -a "$OUT_LOG"
      else
        printf '  %-30s PASS    (changed as expected: was %s, now %s)\n' "$label" "$expected" "$actual" | tee -a "$OUT_LOG"
      fi
      ;;
    increase)
      # numeric comparison
      if awk -v a="$actual" -v e="$expected" 'BEGIN{exit !(a > e)}'; then
        printf '  %-30s PASS    (increased: %s -> %s)\n' "$label" "$expected" "$actual" | tee -a "$OUT_LOG"
      else
        printf '  %-30s FAIL    (expected increase: was %s, now %s)\n' "$label" "$expected" "$actual" | tee -a "$OUT_LOG"
      fi
      ;;
  esac
}

log "VECRM S20 Gate 7 — Post-upgrade verification"
log "Baseline: $BASELINE"
log "Run stamp: $STAMP"
log "Output log: $OUT_LOG"

bar "1. Host identity and uptime"
log "Hostname now: $(hostname)"
BASELINE_HOST="$(baseline_get snapshot_host)"
log "Hostname baseline: $BASELINE_HOST"
log "Uptime now: $(uptime -p)"
log "Uptime since: $(uptime -s)"
# Uptime SHOULD have reset (reboot happened) — adjudicate uptime_since is newer than baseline
BASELINE_UPTIME="$(baseline_get uptime_since)"
log "Uptime baseline (pre-reboot): $BASELINE_UPTIME"

bar "2. Memory + swap (THE upgrade target — expected to INCREASE)"
free -h | tee -a "$OUT_LOG"
ACTUAL_MEM_GB="$(awk -v k="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)" 'BEGIN{printf "%.2f", k/1024/1024}')"
BASELINE_MEM_GB="$(baseline_get mem_total_gb)"
adj "RAM total (GB)" "$BASELINE_MEM_GB" "$ACTUAL_MEM_GB" "increase"

ACTUAL_SWAP_GB="$(awk -v k="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)" 'BEGIN{printf "%.2f", k/1024/1024}')"
BASELINE_SWAP_GB="$(baseline_get swap_total_gb)"
adj "Swap total (GB)" "$BASELINE_SWAP_GB" "$ACTUAL_SWAP_GB" "same"

bar "3. Kernel + OS (expected SAME — Contabo upgrade should not reprovision)"
ACTUAL_UNAME="$(uname -a)"
BASELINE_UNAME="$(baseline_get uname_a)"
adj "Kernel/uname" "$BASELINE_UNAME" "$ACTUAL_UNAME" "same"

if command -v lsb_release >/dev/null 2>&1; then
  ACTUAL_LSB="$(lsb_release -d | cut -f2-)"
  BASELINE_LSB="$(baseline_get lsb_description)"
  adj "OS release" "$BASELINE_LSB" "$ACTUAL_LSB" "same"
fi

bar "4. CPU (may change — VPS 10 SSD -> 20 SSD could re-allocate CPU)"
ACTUAL_CPU="$(nproc)"
BASELINE_CPU="$(baseline_get cpu_count_logical)"
if [ "$ACTUAL_CPU" = "$BASELINE_CPU" ]; then
  log "  CPU count                      INFO    (unchanged: $ACTUAL_CPU logical)"
else
  log "  CPU count                      CHANGE  (was $BASELINE_CPU, now $ACTUAL_CPU)"
fi

ACTUAL_CPU_MODEL="$(grep -m1 '^model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
BASELINE_CPU_MODEL="$(baseline_get cpu_model)"
if [ "$ACTUAL_CPU_MODEL" = "$BASELINE_CPU_MODEL" ]; then
  log "  CPU model                      INFO    (unchanged)"
else
  log "  CPU model                      CHANGE  (was: $BASELINE_CPU_MODEL)"
  log "                                          (now: $ACTUAL_CPU_MODEL)"
fi

bar "5. Disk (root may grow — Contabo mentioned additional disk needs partition extension)"
echo "--- df -h root + /opt ---" | tee -a "$OUT_LOG"
df -h / /opt 2>/dev/null | tee -a "$OUT_LOG"
ACTUAL_ROOT_AVAIL="$(df -B1 / | awk 'NR==2 {print $4}')"
BASELINE_ROOT_AVAIL="$(baseline_get root_avail_bytes)"
log "  Root available bytes:"
log "    baseline: $BASELINE_ROOT_AVAIL"
log "    actual:   $ACTUAL_ROOT_AVAIL"
log "  (Contabo: partition extension is manual — expected SAME until you extend)"

bar "6. Docker fleet — counts"
ACTUAL_VECRM="$(docker ps --filter 'name=vecrm-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
ACTUAL_VEMIO="$(docker ps --filter 'name=vemio-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
ACTUAL_HELPDESK="$(docker ps --filter 'name=helpdesk' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
BASELINE_VECRM="$(baseline_get vecrm_running)"
BASELINE_VEMIO="$(baseline_get vemio_running)"
BASELINE_HELPDESK="$(baseline_get helpdesk_running)"
adj "vecrm running"    "$BASELINE_VECRM"    "$ACTUAL_VECRM"    "same"
adj "vemio running"    "$BASELINE_VEMIO"    "$ACTUAL_VEMIO"    "same"
adj "helpdesk running" "$BASELINE_HELPDESK" "$ACTUAL_HELPDESK" "same"

bar "7. Docker fleet — restart policy adjudication"
log "Pre-upgrade: 36 restart-safe, 2 restart-unsafe (the 2 unsafe = configurators, expected exited(0))"
echo "--- name | restart-policy | status ---" | tee -a "$OUT_LOG"
EXITED_UNEXPECTED=0
for n in $(docker ps -a --format '{{.Names}}'); do
  policy="$(docker inspect "$n" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)"
  status="$(docker inspect "$n" --format '{{.State.Status}}' 2>/dev/null)"
  exit_code="$(docker inspect "$n" --format '{{.State.ExitCode}}' 2>/dev/null)"
  printf '  %-40s %-15s %-10s exit=%s\n' "$n" "$policy" "$status" "$exit_code" | tee -a "$OUT_LOG"
  # If a non-configurator container is exited with non-zero, that's a real failure
  if [ "$status" = "exited" ]; then
    if [[ "$n" != *"configurator"* ]]; then
      if [ "$exit_code" != "0" ]; then
        EXITED_UNEXPECTED=$((EXITED_UNEXPECTED + 1))
      fi
    fi
    # Even configurators should be exit code 0
    if [[ "$n" == *"configurator"* ]] && [ "$exit_code" != "0" ]; then
      EXITED_UNEXPECTED=$((EXITED_UNEXPECTED + 1))
      log "  ⚠ configurator $n exited non-zero ($exit_code) — investigate"
    fi
  fi
done
if [ "$EXITED_UNEXPECTED" -gt 0 ]; then
  log "FAIL: $EXITED_UNEXPECTED container(s) exited unexpectedly"
else
  log "PASS: all non-running containers are expected configurators with exit code 0"
fi

bar "8. Health snapshot"
docker ps --format 'table {{.Names}}\t{{.Status}}' | tee -a "$OUT_LOG"
ACTUAL_HEALTHY="$(docker ps --format '{{.Names}}\t{{.Status}}' | grep -c '(healthy)' || true)"
ACTUAL_UNHEALTHY="$(docker ps --format '{{.Names}}\t{{.Status}}' | grep -c '(unhealthy)' || true)"
BASELINE_HEALTHY="$(baseline_get containers_healthy)"
BASELINE_UNHEALTHY="$(baseline_get containers_unhealthy)"
log "Healthy containers   baseline: $BASELINE_HEALTHY    actual: $ACTUAL_HEALTHY"
log "Unhealthy containers baseline: $BASELINE_UNHEALTHY    actual: $ACTUAL_UNHEALTHY"
log "Note: vemio-freeradius is known-benign unhealthy (S64 carry-forward)"

bar "9. Key SHAs (must be unchanged — reboot should not alter image identity)"
ACTUAL_IMAGE_SHA="$(docker inspect vecrm-backend-1 --format '{{.Image}}' 2>/dev/null)"
BASELINE_IMAGE_SHA="$(baseline_get vecrm_backend_image_sha)"
adj "vecrm-backend image SHA" "$BASELINE_IMAGE_SHA" "$ACTUAL_IMAGE_SHA" "same"

ACTUAL_ALLOCATOR="$(docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py 2>/dev/null | awk '{print $1}')"
BASELINE_ALLOCATOR="$(baseline_get vecrm_allocator_sha256)"
adj "Allocator sha256" "$BASELINE_ALLOCATOR" "$ACTUAL_ALLOCATOR" "same"

# Also verify git side per VECRM-L8
GIT_ALLOCATOR_SHA="$(sha256sum /opt/vecrm/vecrm-src/vecrm/vecrm/voucher_counter.py 2>/dev/null | awk '{print $1}')"
if [ "$ACTUAL_ALLOCATOR" = "$GIT_ALLOCATOR_SHA" ]; then
  log "  VECRM-L8 dual-surface          PASS    (git = container)"
else
  log "  VECRM-L8 dual-surface          FAIL    (git=$GIT_ALLOCATOR_SHA container=$ACTUAL_ALLOCATOR)"
fi

ACTUAL_GIT_HEAD="$(git -C /opt/vecrm/vecrm-src rev-parse HEAD 2>/dev/null)"
BASELINE_GIT_HEAD="$(baseline_get vecrm_git_head)"
adj "vecrm git HEAD" "$BASELINE_GIT_HEAD" "$ACTUAL_GIT_HEAD" "same"

bar "10. Voucher counters (must be unchanged — 0 -> 0)"
COUNTER_OUT="$(printf '%s\n' "SELECT name, last_value FROM \`tabVECRM Voucher Counter\` WHERE name IN ('LEAD-26-27','INQ-26-27');" \
  | docker exec -i vecrm-db-1 bash -lc "MYSQL_PWD=\$(cat /run/secrets/db_root_password 2>/dev/null || echo \"\$MYSQL_ROOT_PASSWORD\") mariadb -uroot -N _02c50791cf17d9de" 2>/dev/null)"
echo "$COUNTER_OUT" | tee -a "$OUT_LOG"
ACTUAL_LEAD="$(echo "$COUNTER_OUT" | awk '/^LEAD-26-27/ {print $2}')"
ACTUAL_INQ="$(echo "$COUNTER_OUT" | awk '/^INQ-26-27/ {print $2}')"
BASELINE_LEAD="$(baseline_get counter_lead_26_27)"
BASELINE_INQ="$(baseline_get counter_inq_26_27)"
adj "LEAD-26-27" "$BASELINE_LEAD" "${ACTUAL_LEAD:-UNREAD}" "same"
adj "INQ-26-27"  "$BASELINE_INQ"  "${ACTUAL_INQ:-UNREAD}"  "same"

bar "11. vecrm dual-200 reachability"
ROOT_STATUS="$(curl -sk -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/ 2>/dev/null || echo 000)"
log "  vecrm root (127.0.0.1:8091/)   $ROOT_STATUS  (expected: 200)"
HASHED_ASSET="$(docker exec vecrm-frontend-1 sh -c 'ls /usr/share/nginx/html/assets/*.js 2>/dev/null | head -1' 2>/dev/null)"
if [ -n "$HASHED_ASSET" ]; then
  ASSET_PATH="${HASHED_ASSET#/usr/share/nginx/html}"
  ASSET_STATUS="$(curl -sk -o /dev/null -w '%{http_code}' "http://127.0.0.1:8091${ASSET_PATH}" 2>/dev/null || echo 000)"
  log "  hashed asset                   $ASSET_STATUS  (expected: 200)"
else
  log "  hashed asset                   SKIP   (could not locate)"
fi

bar "12. SSH and network sanity"
log "Public IP (per ip route):"
ip route get 1.1.1.1 2>/dev/null | head -1 | tee -a "$OUT_LOG"
log "Listening ports (relevant):"
ss -tlnp 2>/dev/null | grep -E ':(22|80|443|8091|3306|6379|5432) ' | tee -a "$OUT_LOG"

bar "ADJUDICATION SUMMARY"
log ""
log "Bank PASS overall if ALL of these hold:"
log "  - RAM increased from $BASELINE_MEM_GB GB to >=10 GB"
log "  - kernel/OS unchanged"
log "  - fleet counts match baseline (9/18/9)"
log "  - no unexpected exited containers"
log "  - vecrm-backend image SHA unchanged"
log "  - allocator sha256 unchanged + VECRM-L8 dual-surface PASS"
log "  - vecrm git HEAD unchanged (47e26da)"
log "  - voucher counters both 0"
log "  - vecrm dual-200 PASS"
log ""
log "If any FAIL: stop and surface BEFORE declaring Gate 7 closed."
log ""
log "Log saved: $OUT_LOG"
