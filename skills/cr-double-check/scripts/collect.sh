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
#   <pr-ref>: https://github.com/owner/repo/pull/123 | owner/repo#123 | 123 (repo of the cwd)
set -euo pipefail

ref="${1:?usage: collect.sh <pr-ref> <bundle-dir>}"
out="${2:?usage: collect.sh <pr-ref> <bundle-dir>}"

case "$ref" in
  https://github.com/*/pull/*)
    path="${ref#https://github.com/}"
    repo="$(printf '%s' "$path" | cut -d/ -f1-2)"
    num="$(printf '%s' "$path" | cut -d/ -f4 | tr -cd '0-9')"
    ;;
  */*#*)
    repo="${ref%%#*}"
    num="${ref##*#}"
    ;;
  *)
    repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
    num="$ref"
    ;;
esac

case "$num" in
  ''|*[!0-9]*) echo "collect: could not read a PR number from '$ref'" >&2; exit 1 ;;
esac

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
