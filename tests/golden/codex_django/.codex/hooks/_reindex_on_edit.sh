#!/usr/bin/env bash
# Coding OS — the shared body of the two edit-time reindex hooks: sourced by
# auto-reindex-docs.sh (docs module: the doc-search chunks of an edited .md) and
# auto-reindex-graph.sh (graph module: the nodes and edges of any routed file)
# after each has sourced cos-env.sh, so either one switches off with its own
# module. Never run directly, never registered in registry.yaml.
#
# Trailing-edge debounce: each edit stamps the path's marker with a fresh token
# and schedules a worker that waits out a quiet window, then runs only if no
# later edit restamped it. A burst of edits indexes the LAST content once; the
# leading-edge skip this replaced indexed the first edit and dropped the rest.

_REINDEX_QUIET_SECONDS=1
# This file is sourced from its real directory, so core is one level up even
# when the calling hook is a consumer's symlink.
_REINDEX_CORE_GUESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"

cos_reindex_on_edit() {
  local hook_id="$1" layer="$2" file_path="$3"
  cos_log_hook "$hook_id" fire "file=${file_path}"
  local project_root="${COS_PROJECT_ROOT:-$PWD}"
  local state_dir="${COS_STATE_DIR:-${project_root}/.coding-os}"
  local core_dir="" candidate
  for candidate in "${COS_CORE_DIR:-}" "${_REINDEX_CORE_GUESS:-}" "${project_root}/src/core" "${project_root}/core"; do
    if [[ -n "$candidate" && -d "${candidate}/graph_os" ]]; then
      core_dir="$(cd "$candidate" && pwd)"
      break
    fi
  done
  if [[ -z "$core_dir" ]]; then
    cos_log_hook "$hook_id" skip "reason=no_core_dir"
    return 0
  fi

  local marker token err_log python
  # Keyed by a checksum of the path: a long path must not overflow a file name.
  marker="${state_dir}/.reindex-pending-${layer}-$(printf '%s' "$file_path" | cksum | cut -d' ' -f1)"
  token="$$-${RANDOM}"
  err_log="${state_dir}/.reindex-errors.log"
  mkdir -p "$state_dir" 2>/dev/null || return 0
  printf '%s' "$token" > "$marker" 2>/dev/null || return 0
  # The interpreter cos itself runs on: a bare system python3 lacks tree-sitter,
  # and every extractor would fall back to regex.
  python="${COS_PYTHON:-$(cos_resolve_python 2>/dev/null || true)}"
  (
    sleep "$_REINDEX_QUIET_SECONDS"
    [[ "$(cat "$marker" 2>/dev/null)" == "$token" ]] || exit 0
    "${python:-python3}" -c '
import os
import sys

core, path, root, layer = sys.argv[1:5]
sys.path[:0] = [core + "/thinking_os", core]
try:
    from graph_os.tools.reindex_dispatch import dispatch

    report = dispatch(
        path,
        project_root=root,
        db_path=os.environ.get("COS_DB_PATH"),
        include_docs=layer == "docs",
        include_graph=layer == "graph",
    )
    if report.get("status") != "skipped" and report.get("cache") != "hit":
        print(
            "[auto-reindex] %s %s: %s (%sms)"
            % (layer, report.get("status"), report.get("path"), report.get("duration_ms")),
            file=sys.stderr,
        )
except Exception as exc:
    print("[auto-reindex] %s ERROR: %s: %s" % (layer, type(exc).__name__, exc), file=sys.stderr)
' "$core_dir" "$file_path" "$project_root" "$layer" 2>>"$err_log"
  ) </dev/null >/dev/null 2>&1 &

  if [[ -f "$err_log" ]] && (( $(wc -l < "$err_log") > 200 )); then
    tail -n 200 "$err_log" > "${err_log}.tmp" && mv "${err_log}.tmp" "$err_log"
  fi
  cos_log_hook "$hook_id" dispatched "file=${file_path}"
  cos_record_activity "$layer" "reindex ${file_path##*/}" 2>/dev/null || true
  printf '{"systemMessage":%s}' "$(printf '[%s] reindex %s' "$layer" "${file_path##*/}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
}
