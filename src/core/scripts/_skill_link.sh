# shellcheck shell=bash
# Skill folder links, sourced by install-adapter.sh and link-stack-skills.sh.
# Python twin: cli._skill_project.link_skill_dir / unlink_skill_dir.
# Spec: docs/engineering/skill-architecture.md (whole-folder skill links).

_cos_only_links() {
  local entry
  for entry in "$1"/* "$1"/.[!.]*; do
    [[ -L "$entry" || ! -e "$entry" ]] || return 1
  done
}

_cos_clear_link_dir() {
  local entry
  for entry in "$1"/* "$1"/.[!.]*; do
    [[ -L "$entry" ]] && rm -f "$entry"
  done
  rmdir "$1" 2>/dev/null || true
}

# cos_link_skill_dir <source_dir> <dest>: dest becomes a link to the whole
# folder. Codex skips a SKILL.md that is itself a link but follows a linked
# folder. A dir holding a real file is a user edit and stays.
cos_link_skill_dir() {
  local source="${1%/}" dest="$2"
  if [[ -d "$dest" && ! -L "$dest" ]]; then
    _cos_only_links "$dest" || return 0
    _cos_clear_link_dir "$dest"
  fi
  mkdir -p "$(dirname "$dest")"
  ln -sfn "$source" "$dest"
}

# cos_unlink_skill_dir <dest>: remove a folder link or a legacy dir of links.
cos_unlink_skill_dir() {
  local dest="$1"
  if [[ -L "$dest" ]]; then
    rm -f "$dest"
  elif [[ -d "$dest" ]] && _cos_only_links "$dest"; then
    _cos_clear_link_dir "$dest"
  fi
}
