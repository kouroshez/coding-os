#!/usr/bin/env bash
# Coding OS — the shared body of the reindex hooks: sourced by
# auto-reindex-docs.sh (docs module: the doc-search chunks of an edited .md),
# auto-reindex-graph.sh (graph module: the nodes and edges of any routed file)
# and auto-graph-reconcile-shell.sh (a shell rm/mv/cp/git), after each has
# sourced cos-env.sh, so each switches off with its own module. Never run
# directly, never registered in registry.yaml.
#
# Trailing-edge debounce: each edit stamps the path's marker with a fresh token
# and schedules a worker that waits out a quiet window, then runs only if no
# later edit restamped it. A burst of edits indexes the LAST content once; the
# leading-edge skip this replaced indexed the first edit and dropped the rest.

_REINDEX_QUIET_SECONDS=1
# This file is sourced from its real directory, so core is one level up even
# when the calling hook is a consumer's symlink.
_REINDEX_CORE_GUESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"

# dispatch() for each path in order; layer is docs, graph or all. A deleted
# path goes through dispatch too: it prunes the file, re-reads its dependents
# and relinks — what a bare DELETE of its rows never did.
# shellcheck disable=SC2016
_REINDEX_WORKER='
import os
import sys

core, root, layer, force = sys.argv[1:5]
sys.path[:0] = [core + "/thinking_os", core]
try:
    if sys.version_info < (3, 10):
        raise RuntimeError("%s is Python %d.%d; graph_os needs 3.10+" % ((sys.executable,) + sys.version_info[:2]))
    from graph_os import tree_sitter_overlay

    # Without the parsers every extractor falls back to regex, and the
    # rebuilt file would replace a parsed graph with a thinner one.
    parsed = tree_sitter_overlay.is_available()
    if layer == "graph" and not parsed:
        raise RuntimeError("%s has no tree-sitter; graph left as it was" % sys.executable)
    from graph_os.tools.reindex_dispatch import dispatch

    for path in sys.argv[5:]:
        report = dispatch(
            path,
            project_root=root,
            db_path=os.environ.get("COS_DB_PATH"),
            include_docs=layer != "graph",
            include_graph=layer != "docs" and parsed,
            force=force == "1",
        )
        for name, outcome in report.get("layers", {}).items():
            if outcome.get("cache") == "hit":
                continue
            print(
                "[auto-reindex] %s %s: %s (%sms)%s"
                % (
                    name,
                    outcome.get("status", report.get("status")),
                    report.get("path"),
                    report.get("duration_ms"),
                    " " + str(outcome["reason"]) if outcome.get("reason") else "",
                ),
                file=sys.stderr,
            )
except Exception as exc:
    print("[auto-reindex] %s ERROR: %s: %s" % (layer, type(exc).__name__, exc), file=sys.stderr)
'

# Sets REINDEX_ROOT, REINDEX_STATE, REINDEX_CORE, REINDEX_PYTHON and
# REINDEX_ERR_LOG; returns 1 when no graph_os core is reachable.
cos_reindex_context() {
  # cos-env.sh already walked up to the project for COS_STATE_DIR; a hook often
  # runs with its cwd in a subdirectory, so $PWD is only the last resort.
  REINDEX_ROOT="${COS_PROJECT_ROOT:-${CLAUDE_PROJECT_DIR:-}}"
  if [[ -z "$REINDEX_ROOT" && "${COS_STATE_DIR:-}" == */.coding-os ]]; then
    REINDEX_ROOT="$(dirname "$COS_STATE_DIR")"
  fi
  REINDEX_ROOT="${REINDEX_ROOT:-$PWD}"
  REINDEX_STATE="${COS_STATE_DIR:-${REINDEX_ROOT}/.coding-os}"
  REINDEX_ERR_LOG="${REINDEX_STATE}/.reindex-errors.log"
  REINDEX_CORE=""
  local candidate
  for candidate in "${COS_CORE_DIR:-}" "${_REINDEX_CORE_GUESS:-}" "${REINDEX_ROOT}/src/core" "${REINDEX_ROOT}/core"; do
    if [[ -n "$candidate" && -d "${candidate}/graph_os" ]]; then
      REINDEX_CORE="$(cd "$candidate" && pwd)"
      break
    fi
  done
  [[ -n "$REINDEX_CORE" ]] || return 1
  # The interpreter cos itself runs on: a bare system python3 lacks tree-sitter,
  # and every extractor would fall back to regex.
  REINDEX_PYTHON="${COS_PYTHON:-$(cos_resolve_python 2>/dev/null || true)}"
  REINDEX_PYTHON="${REINDEX_PYTHON:-python3}"
  mkdir -p "$REINDEX_STATE" 2>/dev/null || return 1
}

_cos_trim_reindex_log() {
  if [[ -f "$REINDEX_ERR_LOG" ]] && (( $(wc -l < "$REINDEX_ERR_LOG") > 200 )); then
    tail -n 200 "$REINDEX_ERR_LOG" > "${REINDEX_ERR_LOG}.tmp" && mv "${REINDEX_ERR_LOG}.tmp" "$REINDEX_ERR_LOG"
  fi
}

cos_reindex_on_edit() {
  local hook_id="$1" layer="$2" file_path="$3"
  cos_log_hook "$hook_id" fire "file=${file_path}"
  if ! cos_reindex_context; then
    cos_log_hook "$hook_id" skip "reason=no_core_dir"
    return 0
  fi

  local marker token
  # Keyed by a checksum of the path: a long path must not overflow a file name.
  marker="${REINDEX_STATE}/.reindex-pending-${layer}-$(printf '%s' "$file_path" | cksum | cut -d' ' -f1)"
  token="$$-${RANDOM}"
  printf '%s' "$token" > "$marker" 2>/dev/null || return 0
  (
    sleep "$_REINDEX_QUIET_SECONDS"
    [[ "$(cat "$marker" 2>/dev/null)" == "$token" ]] || exit 0
    "$REINDEX_PYTHON" -c "$_REINDEX_WORKER" "$REINDEX_CORE" "$REINDEX_ROOT" "$layer" 0 "$file_path" 2>>"$REINDEX_ERR_LOG"
  ) </dev/null >/dev/null 2>&1 &

  _cos_trim_reindex_log
  cos_log_hook "$hook_id" dispatched "file=${file_path}"
  cos_record_activity "$layer" "reindex ${file_path##*/}" 2>/dev/null || true
  printf '{"systemMessage":%s}' "$(printf '[%s] reindex %s' "$layer" "${file_path##*/}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
}

# One detached worker re-reads `paths` in the order given, both layers, forced:
# the reconcile hook passes the gone paths first, so a prune and a reindex of
# the same tree never interleave.
cos_reindex_paths() {
  local hook_id="$1"
  shift
  if ! cos_reindex_context; then
    cos_log_hook "$hook_id" skip "reason=no_core_dir"
    return 0
  fi
  (
    "$REINDEX_PYTHON" -c "$_REINDEX_WORKER" "$REINDEX_CORE" "$REINDEX_ROOT" all 1 "$@" 2>>"$REINDEX_ERR_LOG"
  ) </dev/null >/dev/null 2>&1 &
  _cos_trim_reindex_log
}
