#!/usr/bin/env bash
# VECRM S20 Gate 2 — Pre-upgrade snapshot
# Captures host + fleet state BEFORE Contabo actions the 8 → 12 GB upgrade.
# Pure observation. No mutations. Run once, archive output.
#
# Output is appended to a timestamped log and to a structured baseline file
# that Gate 7's post-upgrade-verify script will diff against.
#
# Expected runtime: < 10 seconds.
# Run AS SOON AS POSSIBLE — Contabo gave no ETA and may reboot at any moment.

set -u  # do NOT set -e — we want every probe to run

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="/opt/vecrm/.s20_pre_upgrade_snapshot_${STAMP}"
mkdir -p "$OUT_DIR"

LOG="${OUT_DIR}/snapshot.log"
BASELINE="${OUT_DIR}/baseline.kv"   # key=value pairs Gate 7 will parse

# kv() writes a structured baseline line AND echoes it to the human log.
kv() {
  printf '%s=%s\n' "$1" "$2" >> "$BASELINE"
  printf '  %-40s %s\n' "$1" "$2" | tee -a "$LOG"
}

bar() { printf '\n========== %s ==========\n' "$1" | tee -a "$LOG"; }

bar "0. Snapshot identity"
kv "snapshot_stamp" "$STAMP"
kv "snapshot_host" "$(hostname)"
kv "snapshot_ssh_from" "${SSH_CLIENT%% *}"

bar "1. Kernel + OS"
kv "uname_a" "$(uname -a)"
if command -v lsb_release >/dev/null 2>&1; then
  kv "lsb_description" "$(lsb_release -d | cut -f2-)"
else
  kv "os_release_pretty" "$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '\"')"
fi
kv "uptime_pretty" "$(uptime -p)"
kv "uptime_since" "$(uptime -s)"

bar "2. Memory + swap (THE upgrade target)"
echo "--- raw free -h ---" | tee -a "$LOG"
free -h | tee -a "$LOG"
# Parse total RAM and total swap as canonical numbers Gate 7 can diff against.
MEM_TOTAL_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
SWAP_TOTAL_KB="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
MEM_TOTAL_GB="$(awk -v k="$MEM_TOTAL_KB" 'BEGIN{printf "%.2f", k/1024/1024}')"
SWAP_TOTAL_GB="$(awk -v k="$SWAP_TOTAL_KB" 'BEGIN{printf "%.2f", k/1024/1024}')"
kv "mem_total_kb"  "$MEM_TOTAL_KB"
kv "mem_total_gb"  "$MEM_TOTAL_GB"
kv "swap_total_kb" "$SWAP_TOTAL_KB"
kv "swap_total_gb" "$SWAP_TOTAL_GB"
echo "--- meminfo head ---" | tee -a "$LOG"
head -5 /proc/meminfo | tee -a "$LOG"

bar "3. CPU"
kv "cpu_count_logical" "$(nproc)"
kv "cpu_model" "$(grep -m1 '^model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"

bar "4. Disk"
echo "--- df -h (root + /opt) ---" | tee -a "$LOG"
df -h / /opt 2>/dev/null | tee -a "$LOG"
ROOT_USED="$(df -B1 / | awk 'NR==2 {print $3}')"
ROOT_AVAIL="$(df -B1 / | awk 'NR==2 {print $4}')"
kv "root_used_bytes"  "$ROOT_USED"
kv "root_avail_bytes" "$ROOT_AVAIL"

bar "5. Docker fleet — counts"
VECRM_RUNNING="$(docker ps --filter 'name=vecrm-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
VEMIO_RUNNING="$(docker ps --filter 'name=vemio-' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
HELPDESK_RUNNING="$(docker ps --filter 'name=helpdesk' --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
TOTAL_RUNNING="$(docker ps --filter 'status=running' --format '{{.Names}}' | wc -l | tr -d ' ')"
TOTAL_ALL="$(docker ps -a --format '{{.Names}}' | wc -l | tr -d ' ')"
kv "vecrm_running"    "$VECRM_RUNNING"
kv "vemio_running"    "$VEMIO_RUNNING"
kv "helpdesk_running" "$HELPDESK_RUNNING"
kv "total_running"    "$TOTAL_RUNNING"
kv "total_all"        "$TOTAL_ALL"

bar "6. Docker fleet — restart policies (matters for post-reboot recovery)"
echo "--- name | restart-policy | status ---" | tee -a "$LOG"
docker ps -a --format '{{.Names}}' | while IFS= read -r name; do
  [ -z "$name" ] && continue
  policy="$(docker inspect "$name" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)"
  status="$(docker inspect "$name" --format '{{.State.Status}}' 2>/dev/null)"
  printf '  %-40s %-12s %s\n' "$name" "$policy" "$status" | tee -a "$LOG"
done
# Count how many containers have a restart policy that survives reboot.
# 'always' and 'unless-stopped' auto-start; 'no' and 'on-failure' do NOT
# guarantee return after a host reboot (on-failure only restarts on non-zero exit).
RESTART_SAFE="$(docker ps -a --format '{{.Names}}' | while IFS= read -r n; do
  p="$(docker inspect "$n" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)"
  [ "$p" = "always" ] || [ "$p" = "unless-stopped" ] && echo "$n"
done | wc -l | tr -d ' ')"
RESTART_UNSAFE="$(docker ps -a --format '{{.Names}}' | while IFS= read -r n; do
  p="$(docker inspect "$n" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)"
  [ "$p" != "always" ] && [ "$p" != "unless-stopped" ] && echo "$n"
done | wc -l | tr -d ' ')"
kv "containers_restart_safe"   "$RESTART_SAFE"
kv "containers_restart_unsafe" "$RESTART_UNSAFE"

bar "7. Docker fleet — health snapshot"
echo "--- name | status ---" | tee -a "$LOG"
docker ps --format 'table {{.Names}}\t{{.Status}}' | tee -a "$LOG"
UNHEALTHY="$(docker ps --format '{{.Names}}\t{{.Status}}' | grep -c '(unhealthy)' || true)"
HEALTHY="$(docker ps --format '{{.Names}}\t{{.Status}}' | grep -c '(healthy)' || true)"
kv "containers_healthy"   "$HEALTHY"
kv "containers_unhealthy" "$UNHEALTHY"

bar "8. Key SHAs (must be unchanged at Gate 7)"
VECRM_IMAGE_SHA="$(docker inspect vecrm-backend-1 --format '{{.Image}}' 2>/dev/null)"
kv "vecrm_backend_image_sha" "$VECRM_IMAGE_SHA"

ALLOCATOR_SHA="$(docker exec vecrm-backend-1 sha256sum /home/frappe/frappe-bench/apps/vecrm/vecrm/vecrm/voucher_counter.py 2>/dev/null | awk '{print $1}')"
kv "vecrm_allocator_sha256" "$ALLOCATOR_SHA"

VECRM_GIT_HEAD="$(git -C /opt/vecrm/vecrm-src rev-parse HEAD 2>/dev/null || echo 'unknown')"
kv "vecrm_git_head" "$VECRM_GIT_HEAD"

bar "9. Voucher counter values (must be unchanged at Gate 7)"
COUNTER_LINES="$(printf '%s\n' "SELECT name, last_value FROM \`tabVECRM Voucher Counter\` WHERE name IN ('LEAD-26-27','INQ-26-27');" \
  | docker exec -i vecrm-db-1 bash -lc "MYSQL_PWD=\$(cat /run/secrets/db_root_password 2>/dev/null || echo \"\$MYSQL_ROOT_PASSWORD\") mariadb -uroot -N _02c50791cf17d9de" 2>/dev/null)"
echo "$COUNTER_LINES" | tee -a "$LOG"
LEAD_COUNTER="$(echo "$COUNTER_LINES" | awk '/^LEAD-26-27/ {print $2}')"
INQ_COUNTER="$(echo "$COUNTER_LINES" | awk '/^INQ-26-27/ {print $2}')"
kv "counter_lead_26_27" "${LEAD_COUNTER:-UNREAD}"
kv "counter_inq_26_27"  "${INQ_COUNTER:-UNREAD}"

bar "DONE"
echo "Snapshot dir:  $OUT_DIR"
echo "Human log:     $LOG"
echo "Baseline file: $BASELINE (Gate 7 verify script will read this)"
echo
echo "Snapshot lines captured:"
wc -l "$BASELINE" "$LOG"
