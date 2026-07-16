---
name: cr-1
description: Baseline code review pass — runs the built-in /code-review skill at xhigh effort against a PR and saves the literal output to /tmp/cr/<repo>/cr_1_<PR>.md. First half of the /cr pipeline; also usable standalone.
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

Run `/code-review xhigh $PR_NUM` and save the output to `$OUT_DIR/cr_1_$PR_NUM.md`.

**Saved file format** (header + literal skill output):

```markdown
# /cr-1 output (baseline review)

**PR:** #<PR_NUM>
**SHA:** <PR head SHA>
**Branch:** <PR head branch>
**Timestamp:** <UTC ISO 8601>
**Skill:** /code-review xhigh

---

<literal output of the code-review skill>

---
<sub>🤖 baseline review · /cr-1</sub>
```

Get the SHA and branch from `gh pr view $PR_NUM --json headRefOid,headRefName`.

**Important:** preserve the skill's output WITHOUT translation or reformatting. Do not invent severities, grouping, or summary tables.
