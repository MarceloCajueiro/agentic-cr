---
name: cr-2
description: Specialized code review pass — runs /pr-review-toolkit:review-pr with aspects picked from the PR diff and saves the literal output to /tmp/cr/<repo>/cr_2_<PR>.md. Second half of the /cr pipeline; also usable standalone.
argument-hint: <PR-number>
user_invocable: true
---

PR_NUM="$ARGUMENTS"

## Don't touch git or the repository files

**This skill is read-only over the repository.** The review output file is the only permitted write.

Before anything else, record where you are:

```bash
git rev-parse --abbrev-ref HEAD   # current branch
git rev-parse HEAD                # current SHA
```

**If the current branch is already the PR head** — the normal case, since whoever runs the review is working on it — the diff is already on disk: `git diff origin/<default-branch>...HEAD`. Don't check out, don't create a branch, don't add a worktree, don't run `stash`/`reset`/`clean`.

Only when the current branch is **not** the PR head, read the diff with `gh pr diff $PR_NUM` — without leaving where you are.

⚠️ **`pr-review-toolkit` has two habits that break this**, and both have happened for real:

1. Its `code-simplifier` sub-agent **edits files** even though the skill is a review. On noticing the edits, the toolkit **rolls the working tree back** to the PR SHA — taking any uncommitted fix from the session owner with it.
2. It **creates its own branch** (e.g. `<pr-branch>-cr2`) and leaves the session on it. Later commits land there, and `git push` on the PR branch answers **"Everything up-to-date"** while the remote stays on the old SHA.

Decline both: if any aspect offers to apply a simplification or fix, **don't apply it** — describe it in the report instead. If `code-simplifier` is the only way to run an aspect, skip that aspect and record why.

When you finish, confirm the branch and SHA match the ones you recorded. If either moved, **go back** (`git checkout <original branch>`) and say so in the output file.

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
