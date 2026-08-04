---
name: cr
description: Full agentic code review pipeline for a GitHub PR — runs two independent review passes in parallel (baseline /code-review + specialized pr-review-toolkit), consolidates them into one deduplicated comment on the PR, then runs a finding-by-finding fix pass. Use when the user wants a PR reviewed end to end, says "/cr", "review this PR", or "run the code review pipeline".
argument-hint: "[PR-number] (default: PR of the current branch)"
user_invocable: true
---

# /cr — full agentic code review pipeline

`$ARGUMENTS` is the PR number. If empty, resolve it from the current branch:

```bash
gh pr view --json number -q .number
```

No PR for the branch: stop and tell the user.

Everything runs against the repository of the current working directory — `gh` infers it from the git remote, so never pass `-R`. Shared file location used by every phase:

```bash
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"
```

## Phase 1 — Reviews in parallel

**Phases 1 and 2 are read-only. No repository file is edited until phase 3.** The underlying skills (`/code-review`, `/pr-review-toolkit:review-pr`) offer to apply fixes on their own: **decline**. Applying between cr-1 and cr-2 invalidates cr-2 — it would review a diff that is no longer the one cr-1 reviewed — and the consolidation then deduplicates against code that already changed.

Precondition: **clean working tree** (`git status --porcelain` empty). Nothing uncommitted may enter phase 1.

**Record the branch and SHA before spawning** — these are what you check against at the end of each phase:

```bash
git rev-parse --abbrev-ref HEAD && git rev-parse HEAD
```

You are normally already on the PR branch. In that case the agents **stay on it**: the diff is on disk (`git diff origin/<default-branch>...HEAD`) and there is nothing to check out.

Both in **isolated agents** (clean context, via the `Agent` tool), in the **same block of tool calls**:

| Agent | Prompt |
|---|---|
| cr-1 | `Invoke the Skill "cr-1" (listed as "agentic-cr:cr-1" when installed as a plugin) with args "<PR_NUM>". Follow the skill to the letter and return only the path of the generated file. You are ALREADY on the PR branch: do NOT check out, do NOT create a branch, do NOT run stash/reset/clean, do NOT edit, commit or push any repository file — if the skill offers to apply fixes, decline. Your only permitted write is the review output file.` |
| cr-2 | `Invoke the Skill "cr-2" (listed as "agentic-cr:cr-2" when installed as a plugin) with args "<PR_NUM>". Follow the skill to the letter and return only the path of the generated file. You are ALREADY on the PR branch: do NOT check out, do NOT create a branch, do NOT run stash/reset/clean, do NOT edit, commit or push any repository file — if the skill offers to apply fixes, decline. Your only permitted write is the review output file.` |

## Phase 2 — Consolidation

Only enter this phase once **both** agents have finished — not before, and with no fix in between.

Verify that `$OUT_DIR/cr_1_<PR_NUM>.md` and `$OUT_DIR/cr_2_<PR_NUM>.md` exist **and that the `SHA` in both headers matches each other and the current PR head** (`gh pr view <PR_NUM> --json headRefOid -q .headRefOid`). Existing is not enough: a file left over from a previous run may be stale. If either file is missing or the SHA diverges, re-run the affected agent(s) — **never consolidate on top of a partial or stale review**. A diverging SHA means code changed mid-cycle: re-run *both* reviews against the current head.

Third isolated agent:

| Agent | Prompt |
|---|---|
| cr-consolidate | `Invoke the Skill "cr-consolidate" (listed as "agentic-cr:cr-consolidate" when installed as a plugin) with args "<PR_NUM>". Return the body of the posted comment. Do NOT edit code: your output is the comment on the PR.` |

Close the phase by confirming **branch, SHA and tree**:

```bash
git status -sb | head -1   # must be the branch recorded in phase 1
git rev-parse HEAD         # must be the same SHA
git status --porcelain     # must still be empty
```

If the branch moved, the agents took you with them (`pr-review-toolkit` creates a `<pr-branch>-cr2` and leaves the session there). Go back before phase 3, or the fix-pass commits land on the agent's branch:

```bash
git checkout <PR branch>
git merge --ff-only <agent branch>   # only if a commit of yours is stuck there
```

**Don't trust the `git push` message:** sitting on the wrong branch, it answers "Everything up-to-date" while the PR stays without the commits. Check the remote SHA with `gh pr view <PR_NUM> --json headRefOid -q .headRefOid`.

## Phase 3 — Fix pass (inline, this session)

**This is the only point in the cycle where code is changed.** Only enter it once the consolidated comment is posted on the PR.

Read the consolidated comment and decide **finding by finding**. Don't apply in bulk, don't dismiss in bulk.

- **CRITICAL / HIGH:** apply, unless proven false positive. Every fix gets (or reuses) a test.
- **MEDIUM / LOW:** apply when the cost is low and the gain is real. Decline when it's out of scope, speculative, or over-engineering — and say why.
- Run the project's test suite after the fixes (find the command in the repo's CLAUDE.md, README, Makefile, package.json, etc.). Separate commit(s): `fix: apply code review findings from PR #<PR_NUM> (<short summary>)` — follow the repository's commit conventions, including language. Push to the PR branch.
- **Confirm the push landed** — the local head and the PR head must match. "Everything up-to-date" is also what you get when you have been committing on the wrong branch:

  ```bash
  git rev-parse HEAD
  gh pr view <PR_NUM> --json headRefOid -q .headRefOid
  ```

Reply **on the PR** (`gh pr comment <PR_NUM> --body-file -`):

```markdown
## Response to the consolidated code review

**Applied:** N
- 🚨 `file.rb:42` — <what changed> (`<sha>`)

**Not applied:** N
- 💡 `file.rb:88` — <finding> → <one-line justification: false positive / out of scope / accepted trade-off>

Test suite green after the fixes: `<test command>` ✅
```

If the repository's PRs and comments are predominantly written in a language other than English, write this reply in that language, keeping the structure.

Close the report saying what was applied, what wasn't and why. Human review proceeds as usual.

---

**Rule that holds across the whole pipeline:** review doesn't edit, the fix pass doesn't review. No code change between the start of cr-1 and the posted consolidated comment — all three reviews must see exactly the same diff. Code changed mid-cycle produces phantom findings, wrong deduplication, and a comment pointing at lines that no longer exist.
