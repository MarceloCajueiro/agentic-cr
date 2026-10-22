#!/usr/bin/env bash
# Fetches everything cr-double-check needs about one PR into a bundle directory,
# read-only, with no clone and no checkout:
#
#   pr.json       gh pr view --json (metadata, files, commits, comments, reviews, CI)
#   diff.patch    gh pr diff (empty when GitHub refuses the diff, see diff.err)
#   events.jsonl  force-push events from the issue timeline, one JSON object per line
#   viewer.txt    the gh login running the check (trusted as a reviewer)
#   repo.txt      owner/repo
#
# Usage: collect.sh <pr-ref> <bundle-dir>
#        collect.sh --resolve <pr-ref>   prints "owner/repo number" and exits, no network
#                                        for a full ref (what tests/run_fixtures.py checks)
#   <pr-ref>: https://github.com/owner/repo/pull/123[/files|#anchor|?query]
#             | owner/repo#123 | 123 (repository of the current directory)
set -euo pipefail

# Only the digits right after /pull/ are the number: a link copied from a comment
# notification ends in #issuecomment-<id>, whose digits must never join it.
resolve() {
  local ref="$1"
  if [[ "$ref" =~ ^https?://(www\.)?github\.com/([^/]+/[^/#?]+)/pull/([0-9]+)([/#?].*)?$ ]]; then
    repo="${BASH_REMATCH[2]}"
    num="${BASH_REMATCH[3]}"
  elif [[ "$ref" =~ ^([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#([0-9]+)$ ]]; then
    repo="${BASH_REMATCH[1]}"
    num="${BASH_REMATCH[2]}"
  elif [[ "$ref" =~ ^#?([0-9]+)$ ]]; then
    repo=""
    num="${BASH_REMATCH[1]}"
  else
    echo "collect: could not read a PR reference from '$ref'" >&2
    return 1
  fi
}

if [ "${1:-}" = "--resolve" ]; then
  resolve "${2:?usage: collect.sh --resolve <pr-ref>}"
  printf '%s %s\n' "${repo:-.}" "$num"
  exit 0
fi

ref="${1:?usage: collect.sh <pr-ref> <bundle-dir>}"
out="${2:?usage: collect.sh <pr-ref> <bundle-dir>}"
resolve "$ref"
[ -n "$repo" ] || repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

mkdir -p "$out"
printf '%s\n' "$repo" > "$out/repo.txt"
gh api user -q .login > "$out/viewer.txt"

gh pr view "$num" -R "$repo" --json \
  number,title,url,state,isDraft,author,body,baseRefName,headRefName,headRefOid,additions,deletions,changedFiles,files,commits,comments,reviews,statusCheckRollup,labels \
  > "$out/pr.json"

# A very large PR has no diff through the API; the skill treats that as "cannot determine".
if ! gh pr diff "$num" -R "$repo" > "$out/diff.patch" 2> "$out/diff.err"; then
  : > "$out/diff.patch"
fi

gh api "repos/$repo/issues/$num/timeline?per_page=100" --paginate \
  --jq '.[] | select(.event == "head_ref_force_pushed") | {event, created_at, actor: .actor.login}' \
  > "$out/events.jsonl"

echo "$out"
