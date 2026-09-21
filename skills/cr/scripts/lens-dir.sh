#!/usr/bin/env bash
# Prints the directory that holds the cr-* lens definitions (one file per lens,
# e.g. cr-verifier.md) and exits 0. Exits 1 with a diagnostic when it cannot find them.
#
# The lenses ship INSIDE this skill (references/lenses/), because a skill installer
# copies the skill directory and nothing outside it. The other candidates cover a
# local checkout of agentic-cr and the skill roots of the harnesses that install
# Agent Skills in a shared location.
#
# Override with CR_LENS_DIR=<dir> when the automatic resolution fails.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(dirname "$here")"

candidates=()
[ -n "${CR_LENS_DIR:-}" ] && candidates+=("$CR_LENS_DIR")

# 1. Bundled with this skill, the path that survives any installer.
candidates+=("$skill_dir/references/lenses")

# 2. Skill roots of the harnesses that share ~/.agents/skills, plus their own.
home_roots=(
  ".agents/skills" ".pi/agent/skills" ".claude/skills" ".config/agents/skills"
  ".codex/skills" ".cursor/skills" ".gemini/skills" ".grok/skills"
  ".config/opencode/skills" ".config/crush/skills"
)
for r in "${home_roots[@]}"; do
  candidates+=("$HOME/$r/cr/references/lenses")
done

# 3. Project scope: every conventional skill root from here up to the git root,
#    plus a local checkout of agentic-cr (skills/cr/references/lenses).
project_roots=(
  ".agents/skills" ".pi/skills" ".claude/skills" ".codex/skills" ".cursor/skills"
  ".gemini/skills" ".grok/skills" ".opencode/skills" ".crush/skills"
)
dir="$(pwd)"
while :; do
  for p in "${project_roots[@]}"; do
    candidates+=("$dir/$p/cr/references/lenses")
  done
  candidates+=("$dir/skills/cr/references/lenses")
  { [ -d "$dir/.git" ] || [ "$dir" = "/" ]; } && break
  dir="$(dirname "$dir")"
done

for d in "${candidates[@]}"; do
  [ -n "$d" ] && [ -f "$d/cr-verifier.md" ] && { printf '%s\n' "$d"; exit 0; }
done

# 4. Last resort: a bounded search across the shared skill roots.
for r in "$HOME/.agents/skills" "$HOME/.pi/agent/skills" "$HOME/.claude/skills"; do
  [ -d "$r" ] || continue
  found="$(find "$r" -name cr-verifier.md -path '*/cr/references/lenses/*' -print -quit 2>/dev/null || true)"
  [ -n "$found" ] && { printf '%s\n' "$(dirname "$found")"; exit 0; }
done

cat >&2 <<'EOF'
lens-dir: could not locate the cr-* lens definitions.
The /cr skill needs them; running the lenses from memory is exactly the failure
this design avoids, so stop and tell the user instead.

Fix by either:
  - reinstalling the skill:  npx skills add MarceloCajueiro/agentic-cr
  - pointing at a copy:      CR_LENS_DIR=/path/to/agentic-cr/skills/cr/references/lenses scripts/lens-dir.sh
EOF
exit 1
