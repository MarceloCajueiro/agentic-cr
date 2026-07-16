---
name: cr-2
description: Specialized code review pass — runs /pr-review-toolkit:review-pr with aspects picked from the PR diff and saves the literal output to /tmp/cr/<repo>/cr_2_<PR>.md. Second half of the /cr pipeline; also usable standalone.
argument-hint: <PR-number>
user_invocable: true
---

PR_NUM="$ARGUMENTS"

Compute the output location (the repository is the one in the current working directory — never pass `-R`):

```bash
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"
mkdir -p "$OUT_DIR"
```

Run `/pr-review-toolkit:review-pr $PR_NUM` and save the output to `$OUT_DIR/cr_2_$PR_NUM.md`. You decide which aspects of the skill to run based on the PR diff (errors/tests/types/comments/code/simplify/all). Use `all` if the diff is large or touches multiple kinds of code; a specific aspect if the diff is focused.

**Saved file format:**

```markdown
# /cr-2 output (specialized review)

**PR:** #<PR_NUM>
**SHA:** <PR head SHA>
**Branch:** <PR head branch>
**Timestamp:** <UTC ISO 8601>
**Aspects run:** <e.g. errors, tests, types — or "all">

---

<literal output of the skill — preserve per-aspect sections if present>

---
<sub>🤖 specialized review · /cr-2</sub>
```

Get the SHA and branch from `gh pr view $PR_NUM --json headRefOid,headRefName`.

**Important:** preserve the skill's output WITHOUT translation or reformatting. If the skill emits its own labels (`Critical` / `Important` / `Suggestions`), keep them literally.
