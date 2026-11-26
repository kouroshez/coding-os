# shellcheck shell=bash
# Skill folder links, sourced by install-adapter.sh and link-stack-skills.sh.
# Python twin: cli._skill_project.link_skill_dir / unlink_skill_dir.
# Spec: docs/engineering/skill-architecture.md (whole-folder skill links).

# A dir is ours to replace only when every entry in it is a link.
_cos_only_links() {
  [[ -z "$(find "$1" -mindepth 1 -maxdepth 1 ! -type l -print -quit 2>/dev/null)" ]]
}

_cos_clear_link_dir() {
  find "$1" -mindepth 1 -maxdepth 1 -type l -delete 2>/dev/null || true
  rmdir "$1" 2>/dev/null || true
}

# A link is cos's when it dangles or resolves inside the coding-os root; any
# other link with a skill's name is the user's and stays.
_cos_owned_link() {
  local link="$1" root target
  target="$(cd -P "$link" 2>/dev/null && pwd)" || return 0
  root="$(cd -P "$2" 2>/dev/null && pwd)" || return 1
  [[ "$target" == "$root"/* ]]
}

# cos_link_skill_dir <source_dir> <dest> <cos_root>: dest becomes a link to the
# whole folder. Codex skips a SKILL.md that is itself a link but follows a
# linked folder. A user's own link, file or dir holding a real file stays.
cos_link_skill_dir() {
  local source="${1%/}" dest="$2" root="$3"
  if [[ -L "$dest" ]]; then
    _cos_owned_link "$dest" "$root" || return 0
  elif [[ -d "$dest" ]]; then
    _cos_only_links "$dest" || return 0
    _cos_clear_link_dir "$dest"
    [[ -e "$dest" ]] && return 0
  elif [[ -e "$dest" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  ln -sfn "$source" "$dest"
}

# cos_unlink_skill_dir <dest> <cos_root>: remove cos's folder link, or a legacy
# dir that holds only links. Never descends a link.
cos_unlink_skill_dir() {
  local dest="$1" root="$2"
  if [[ -L "$dest" ]]; then
    _cos_owned_link "$dest" "$root" && rm -f "$dest"
  elif [[ -d "$dest" ]] && _cos_only_links "$dest"; then
    _cos_clear_link_dir "$dest"
  fi
  return 0
}
