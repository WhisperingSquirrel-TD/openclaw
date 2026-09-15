#!/usr/bin/env bash
# Refresh the QMD core index. QMD's embedding session expires after 30 minutes
# yet exits 0; therefore repeat sessions until qmd status proves Pending: 0.
set -uo pipefail

status_dir=/home/tomdean88/.openclaw/workspace/runtime
status="${status_dir}/qmd-vectorise-status.md"
tmp="${status}.tmp"
qmd=/home/tomdean88/.npm-packages/bin/qmd
index=core
config_dir=/home/tomdean88/.openclaw/workspace/reference/qmd-config
mkdir -p "$status_dir"

# Embedding is intentionally an overnight-only workload. A manual start or
# recovery job outside 22:00–07:29 must defer rather than consume daytime CPU.
now_hm=$(date +%H%M)
if ! (( 10#$now_hm >= 2200 || 10#$now_hm < 730 )); then
  cat > "$status" <<EOF
# QMD Core Vectorisation Status

- State: DEFERRED_TO_QUIET_WINDOW
- Deferred: $(date --iso-8601=seconds)
- Reason: vectorisation is permitted only from 22:00 to 07:29 local time.
- Index: core
- Completion criterion: Pending: 0 plus the core vector retrieval smoke test.
EOF
  exit 0
fi

# Make a live, truthful status visible immediately; the detailed report is
# atomically replaced only once the run has a terminal outcome.
printf '# QMD Core Vectorisation Status\n\n- State: RUNNING\n- Started: %s\n- Index: %s\n- Completion criterion: `Pending: 0`\n' "$(date --iso-8601=seconds)" "$index" > "$status"

update_rc=1; embed_rc=1; status_rc=1; smoke_rc=1; pending=-1; pass=0; rc=1
qmd_cmd() { QMD_LLAMA_GPU=false QMD_CONFIG_DIR="$config_dir" "$qmd" --index "$index" "$@"; }
qmd_pending() {
  local output line
  output=$(qmd_cmd status 2>&1) || return 1
  printf '%s\n' "$output"
  # QMD omits the Pending line entirely once no documents need embedding.
  # Treat that documented zero-pending representation as success, not a
  # verification failure.
  line=$(printf '%s\n' "$output" | sed -r 's/\x1B\[[0-9;]*[[:alpha:]]//g' | grep -E '^[[:space:]]*Pending:' | tail -1 || true)
  if [[ -z $line ]]; then
    printf '%s\n' 0
    return 0
  fi
  [[ $line =~ Pending:[[:space:]]*([0-9]+) ]] || return 3
  printf '%s\n' "${BASH_REMATCH[1]}"
}
{
  echo '# QMD Core Vectorisation Status'
  echo
  echo "- Started: $(date --iso-8601=seconds)"
  echo "- Index: $index"
  echo '- Completion criterion: `Pending: 0`'
  echo
  echo '## Update'
  qmd_cmd update; update_rc=$?
  if [ "$update_rc" -eq 0 ]; then
    echo; echo '## Embedding passes'
    while :; do
      pass=$((pass + 1)); echo "### Pass $pass"
      qmd_cmd embed; embed_rc=$?
      echo "- Embed exit: $embed_rc"; echo '- Status after pass:'
      pending_output=$(qmd_pending); status_rc=$?
      printf '%s\n' "$pending_output"
      if [ "$status_rc" -ne 0 ]; then echo "- Verification failure: status=$status_rc"; break; fi
      pending=$(printf '%s\n' "$pending_output" | tail -1)
      echo "- Pending vectors: $pending"
      if [ "$embed_rc" -ne 0 ] || [ "$pending" -eq 0 ]; then break; fi
      echo '- Work remains; starting another embedding pass.'; echo
    done
  else
    echo; echo '## Embedding passes'; echo 'SKIPPED (update failed)'
  fi
  echo
  if [ "$update_rc" -eq 0 ] && [ "$embed_rc" -eq 0 ] && [ "$status_rc" -eq 0 ] && [ "$pending" -eq 0 ]; then
    echo '## Vector retrieval smoke test'
    echo '- Query: Stackstone Consulting revenue networking prospecting'
    smoke_output=$(qmd_cmd vsearch 'Stackstone Consulting revenue networking prospecting' --json -c workspace-root 2>&1)
    smoke_rc=$?
    printf '%s\n' "$smoke_output"
    if [ "$smoke_rc" -eq 0 ] && printf '%s\n' "$smoke_output" | grep -q 'qmd://workspace-root/'; then
      echo '- Smoke test: PASS (core vector result returned)'
      echo '- Result: SUCCESS (zero pending vectors; retrieval verified)'; rc=0
    else
      echo "- Smoke test: FAIL (exit=$smoke_rc; expected a core vector result)"
      echo '- Result: INCOMPLETE (vectors complete but retrieval verification failed)'
    fi
  else
    echo "- Result: INCOMPLETE (update=$update_rc embed=$embed_rc status=$status_rc pending=$pending)"
  fi
  echo "- Finished: $(date --iso-8601=seconds)"
} > "$tmp" 2>&1
mv "$tmp" "$status"
exit "$rc"
