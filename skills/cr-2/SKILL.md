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

Habit 1 is closed by construction: the aspect list below never names `simplify`, so `code-simplifier` is never spawned. Habit 2 still needs watching — check the branch when you finish.

If any aspect offers to apply a simplification or fix, **don't apply it** — describe it in the report instead.

When you finish, confirm all three — branch, SHA, and a clean tree:

```bash
git rev-parse --abbrev-ref HEAD   # must equal the branch you recorded
git rev-parse HEAD                # must equal the SHA you recorded
git status --porcelain            # must be empty
```

Branch or SHA moved: **go back** (`git checkout <original branch>`) and say so in the output file. Tree dirty: a sub-agent wrote to the repository despite the rules — revert those files, and record which ones under `## Sub-agent edits reverted`. Never end this skill with a dirty tree; the caller's next step assumes the review changed nothing.

Compute the output location (the repository is the one in the current working directory — never pass `-R`):

```bash
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"
mkdir -p "$OUT_DIR"
```

## Which aspects to run

**Never pass `all`, and never pass `simplify`.** `all` expands to include `simplify`, which invokes `code-simplifier` — the agent whose own instructions tell it to edit files autonomously. Naming the aspects explicitly is what keeps this pass read-only; there is no aspect string that both covers everything and stays read-only.

Pick from these five, based on the diff:

| Aspect | Run it when |
|---|---|
| `code` | always — general quality against CLAUDE.md |
| `tests` | the diff adds or changes specs |
| `errors` | the diff touches `rescue`, error handling, or logging |
| `comments` | the diff adds or changes comments or docs |
| `types` | the diff introduces new types or value objects |

For a broad diff, pass all five — that is the read-only equivalent of `all`:

```bash
/pr-review-toolkit:review-pr $PR_NUM code tests errors comments types
```

For a focused diff, pass only what applies. Record in the output file which aspects you ran and why.

Save the output to `$OUT_DIR/cr_2_$PR_NUM.md`.

**If any sub-agent edits a file anyway** — the four aspects other than `comments` have no explicit read-only instruction, so they can — do not commit it and do not let the toolkit roll the tree back. Restore just that file (`git checkout -- <file>`), note it in the report under a `## Sub-agent edits reverted` heading, and continue.

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
