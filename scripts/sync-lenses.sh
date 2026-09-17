#!/usr/bin/env bash
# Regenerates the lens definitions bundled inside skills/cr-single/references/lenses/
# from the canonical agents/cr-*.md.
#
# Why two copies exist:
#   - agents/*.md is what Claude Code registers as subagent types for /cr's fan-out.
#   - skills/cr-single/references/lenses/*.md is what /cr-single reads as checklists,
#     and it must ship INSIDE the skill directory: skill installers (skills.sh,
#     `npx skills add`, manual copies into ~/.agents/skills, ...) copy the skill
#     directory alone, so a path pointing outside it does not survive installation.
#
# Dependency-free on purpose: bash + coreutils/findutils only, no awk, sed or diff.
# The CI job runs on `ubuntu-slim`, whose image ships a deliberately thin package
# set, and the same script has to work on a macOS bash 3.2 box.
#
# Usage:
#   scripts/sync-lenses.sh          # rewrite the bundled copies
#   scripts/sync-lenses.sh --check  # fail (exit 1) if they are out of sync; writes nothing
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/agents"
DST="$ROOT/skills/cr-single/references/lenses"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

[ -d "$SRC" ] || { echo "sync-lenses: $SRC not found" >&2; exit 1; }

# Everything after the closing '---' of the YAML frontmatter, without leading blanks.
body() {
  local line fm=0 started=0
  while IFS= read -r line || [ -n "$line" ]; do
    if [ "$fm" = 0 ]; then
      [ "$line" = "---" ] && fm=1
      continue
    fi
    if [ "$fm" = 1 ]; then
      [ "$line" = "---" ] && fm=2
      continue
    fi
    if [ "$started" = 0 ] && [ -z "$line" ]; then
      continue
    fi
    started=1
    printf '%s\n' "$line"
  done <"$1"
}

render() {
  printf '<!-- Generated from agents/%s by scripts/sync-lenses.sh - do not edit by hand. -->\n\n' "${1##*/}"
  body "$1"
}

# Byte-exact comparison: command substitution drops trailing newlines, so compare the
# size too rather than let a hand-added blank line pass as "in sync".
same() {
  [ "$(wc -c <"$1")" = "$(wc -c <"$2")" ] && [ "$(<"$1")" = "$(<"$2")" ]
}

names=()
for f in "$SRC"/cr-*.md; do
  [ -e "$f" ] || break
  names+=("${f##*/}")
done
if [ "${#names[@]}" = 0 ]; then
  echo "sync-lenses: no cr-*.md in $SRC" >&2
  exit 1
fi

# Every name that is no longer backed by agents/ (a renamed or deleted lens).
orphans() {
  local f name n found
  for f in "$DST"/cr-*.md; do
    [ -e "$f" ] || continue
    name="${f##*/}"
    found=0
    for n in "${names[@]}"; do
      [ "$n" = "$name" ] && found=1
    done
    [ "$found" = 1 ] || printf '%s\n' "$name"
  done
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
for name in "${names[@]}"; do
  render "$SRC/$name" >"$tmp/$name"
done

if [ "$CHECK" = 1 ]; then
  rc=0
  for name in "${names[@]}"; do
    if [ ! -f "$DST/$name" ]; then
      echo "MISSING: skills/cr-single/references/lenses/$name (run scripts/sync-lenses.sh)" >&2
      rc=1
    elif ! same "$tmp/$name" "$DST/$name"; then
      echo "OUT OF SYNC: skills/cr-single/references/lenses/$name (run scripts/sync-lenses.sh)" >&2
      if command -v diff >/dev/null 2>&1; then
        diff -u "$DST/$name" "$tmp/$name" | head -20 >&2 || true
      fi
      rc=1
    fi
  done
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    echo "ORPHAN: skills/cr-single/references/lenses/$name has no agents/$name (run scripts/sync-lenses.sh)" >&2
    rc=1
  done < <(orphans)
  [ "$rc" = 0 ] && echo "lenses in sync (${#names[@]} definitions)"
  exit "$rc"
fi

mkdir -p "$DST"
while IFS= read -r name; do
  [ -n "$name" ] && rm -f "$DST/$name"
done < <(orphans)
for name in "${names[@]}"; do
  cp "$tmp/$name" "$DST/$name"
done
echo "wrote ${#names[@]} lens definitions to skills/cr-single/references/lenses/"
