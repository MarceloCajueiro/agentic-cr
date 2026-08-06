---
name: cr-1
description: Baseline code review pass — runs the built-in /code-review skill at high effort against a PR and saves the literal output to /tmp/cr/<repo>/cr_1_<PR>.md. First half of the /cr pipeline; also usable standalone.
argument-hint: <PR-number>
user_invocable: true
---

PR_NUM="$ARGUMENTS"

## Don't touch git

**This skill is read-only over the repository.** The review output file is the only permitted write.

Before anything else, record where you are:

```bash
git rev-parse --abbrev-ref HEAD   # current branch
git rev-parse HEAD                # current SHA
```

**If the current branch is already the PR head** — the normal case, since whoever runs the review is working on it — the diff is already on disk: `git diff origin/<default-branch>...HEAD`. Don't check out, don't create a branch, don't add a worktree, don't run `stash`/`reset`/`clean`. The `/code-review` skill may offer to do some of this on its own: **decline**.

Only when the current branch is **not** the PR head, read the diff with `gh pr diff $PR_NUM` — without leaving where you are.

When you finish, confirm the branch and SHA are the ones you recorded. If either moved, **go back** (`git checkout <original branch>`) and say so in the output file: the session owner may have uncommitted fixes that a checkout wipes, and a later push would answer "Everything up-to-date" while the PR silently misses the commits.

Compute the output location (the repository is the one in the current working directory — never pass `-R`):

```bash
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"
mkdir -p "$OUT_DIR"
```

Run `/code-review high $PR_NUM` and save the output to `$OUT_DIR/cr_1_$PR_NUM.md`.

**Saved file format** (header + literal skill output):

```markdown
# /cr-1 output (baseline review)

**PR:** #<PR_NUM>
**SHA:** <PR head SHA>
**Branch:** <PR head branch>
**Timestamp:** <UTC ISO 8601>
**Skill:** /code-review high

---

<literal output of the code-review skill>

---
<sub>🤖 baseline review · /cr-1</sub>
```

Get the SHA and branch from `gh pr view $PR_NUM --json headRefOid,headRefName`.

**Important:** preserve the skill's output WITHOUT translation or reformatting. Do not invent severities, grouping, or summary tables.
