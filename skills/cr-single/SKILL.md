---
name: cr-single
description: Agentic code review of a GitHub PR in a SINGLE agent — the same lenses as /cr, applied sequentially in this very session, with no subagents and no Workflow. Disk ledger, batched probes, adversarial verification by execution, one consolidated comment. Read-only by default; with --fix it also runs a finding-by-finding fix pass. Use when the user says "/cr-single", asks for a single-agent review, or wants to A/B this architecture against /cr.
argument-hint: "[PR-number] [--fix] (default: PR of the current branch, review only)"
user_invocable: true
---

# /cr-single — agentic code review in a single agent

Single-agent variant of `/cr`: **everything runs in this session, sequentially** — no subagent, no Workflow, no fan-out. The lenses are the same (`cr-*` agent definitions that ship with this plugin), applied by you as checklists; adversarial verification becomes a discipline of execution instead of an independent agent.

`$ARGUMENTS` holds the PR number and/or the `--fix` flag, in any order — `/cr-single`, `/cr-single 123`, `/cr-single --fix`, `/cr-single 123 --fix` are all valid. Strip the flag before resolving the number:

```bash
FIX=0; case " $ARGUMENTS " in *" --fix "*) FIX=1;; esac
PR_ARG="$(printf '%s' "$ARGUMENTS" | sed 's/--fix//g' | tr -d '[:space:]')"
PR_NUM="${PR_ARG:-$(gh pr view --json number -q .number)}"
```

No PR for the branch: stop and tell the user.

**`--fix` is the only thing that authorizes phase 7.** Without it this command reviews and comments; it never edits, commits or pushes. Carry `FIX` to the end — phase 7 checks it.

Everything runs against the repository of the current working directory — `gh` infers it from the git remote, so **never pass `-R`**. Resolve the default branch and the output directory once:

```bash
BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"; mkdir -p "$OUT_DIR"
```

## Principles

1. **Review does not edit, the fix pass does not review.** No change to any repository file between the start of the triage and the posted comment. Here that is **discipline, not structure** — nothing stops you from using Edit, so the rule is yours to keep: probe files go in the session scratchpad, writes are allowed only under `$OUT_DIR` and the scratchpad, **never inside the repository working tree** (the closing check requires `git status --porcelain` empty).
2. **A finding requires a citable rule OR executable evidence.** With neither, it does not enter the final report. And the rule must be one the *reviewed project* actually wrote — a fabricated citation is worse than a missed finding.
3. **A runtime claim only enters CONFIRMED by execution.** The number one risk of this architecture is self-confirmation: whoever found the finding is the one who judges it. The antidote is not "reread it skeptically" — it is **a probe whose output decides**. A persona does not create independence; execution does.
4. **Partial coverage is declared, never silent** — what was not verified goes under *Verification gaps*.
5. **A lens with nothing to do on this diff does not run.** The triage justifies every pass AND every skip.
6. **A finding goes into the ledger the moment it is born**, not at the end. A long context can be summarized mid-run; what lives only in your head is lost, what lives on disk survives. The final comment is assembled **from the ledger**, never from memory.
7. **Recall posture in the find, rigor in the verify.** A bug candidate with a nameable failure scenario goes into the ledger as `[CANDIDATE]` even without proof — the "rule OR evidence" bar is applied in the verify phase, not during collection. Solo this matters MORE: there is no second lens to catch what you dropped in silence.

## Resolving the lens definitions

The lenses ship with this plugin as `cr-*.md` files. You do not spawn them here — you **read them and apply them**. Locate the directory once, at the start:

```bash
LENS_DIR="${CLAUDE_PLUGIN_ROOT}/agents"
ls "$LENS_DIR"/cr-*.md
```

If that listing is empty or errors — you are running from a local checkout of this plugin rather than an installed copy — the definitions live in the `agents/` directory of the *agentic-cr* checkout, **not** of the repository under review. Locate it (a `find` for `cr-verifier.md` outside the reviewed repo) and confirm the listing before phase 3. **If you cannot find the definitions, stop and tell the user** — running the lenses from memory is exactly the failure this design avoids.

## Preparation

Precondition: **clean working tree** (`git status --porcelain` empty). Record the branch and SHA — they are what you check against at the close:

```bash
git rev-parse --abbrev-ref HEAD && git rev-parse HEAD
```

You are normally already on the PR branch: the diff is on disk (`git diff origin/$BASE...HEAD`) and nobody checks anything out.

Create the **ledger** at `$OUT_DIR/cr_single_${PR_NUM}_ledger.md` (overwrite if it exists) with this skeleton:

```markdown
# Ledger /cr-single — PR #<N> · <branch> · <SHA> · <timestamp>

## Triage
(bucket, passes run, passes skipped — filled in phase 1)

## Diff map
(filled in phase 2)

## Candidates
(one block per candidate, appended as it is found — phase 3)

## Probe questions
(accumulated in phases 2–3, answered in batch in phase 4)

## Verified and dismissed
## Verification gaps
```

Format of each candidate in the ledger (all fields required):

```markdown
### C<n> — `file:line` — <SEV> — <short title>
- **Lens:** <cr-*> · **Status:** CANDIDATE
- **Problem:** <1–2 sentences>
- **Failure scenario:** <concrete input/state → visible consequence>
- **Rule/Evidence:** <one-line citation OR what was read/run — or "(pending probe P<k>)">
- **Refutation attempt:** (pending — filled in phase 5)
```

Before appending, **check for a duplicate**: a candidate in the same file, within ±3 lines, with the same core verb + object is the same entry — add the lens to **Lens:** instead of creating a new one (two lenses landing on the same point is a confirmation signal, not a new finding).

## Phase 1 — Triage: which lenses run, and which do not

Decide from the **final diff**, not from the branch history. Collect the signals in one go:

```bash
gh pr diff "$PR_NUM" --name-only
git diff --stat "origin/$BASE...HEAD"
git diff --unified=0 "origin/$BASE...HEAD" | grep -E '^\+' | grep -cEi 'rescue|except|catch|recover|ensure|finally'   # error handling signal
git diff --unified=0 "origin/$BASE...HEAD" | grep -E '^\+' | grep -cE '^\+\s*(class|struct|record|interface|type) '  # new type signal
```

### Buckets

> The bucket table, the gates and the cut order below are **identical to `/cr`'s**. A recalibration must be applied to both skills — that is the price of the A/B comparison being fair.

| Bucket | Condition | Lens ceiling |
|---|---|---|
| 📄 **docs-only** | every file is Markdown, docs or agent/prompt definitions — **no** executable file | 1–2 |
| 🔹 **trivial** | lockfile or version bump, or ≤10 lines in 1 file | 2 |
| 🔸 **surgical** | ≤ ~40 lines, ≤ 3 files | **≤ 4** |
| 🔶 **feature** | anything larger | **≤ 7** (+ sweep if >400 lines) |

**Hard rule (it precedes the docs gate):** any executable file in the diff — a shell script, a CI workflow, a migration, a template that runs, or any source file — **forbids** docs-only treatment. A PR that looks like docs can carry its Critical inside the one `.sh` nobody read.

### Per-lens gates — RUN if, SKIP if

The SKIP predicate binds as hard as the RUN one: if SKIP matches, the lens **does not run** even when RUN also matches (SKIP is the more specific exception).

| Lens | RUN if | SKIP if |
|---|---|---|
| `cr-boundary-guard` | the diff touches source code containing a query, a request handler, a service or a permission check — **always**, it is the Critical dimension | the diff has no query, model, handler or service (only views, assets, locales, config) |
| `cr-conventions` | the diff touches source code — **always** | nothing (it is the base lens of every code PR) |
| `cr-code-reviewer` | bucket **feature** | surgical/trivial/docs bucket — a generalist is redundant with boundary-guard plus conventions on a small diff |
| `cr-data-layer` | the diff adds or changes a query, a scope, a query object or a report that builds one; **or** touches a migration, the schema dump, or writes data in bulk bypassing the model layer | the query change is only a rename or column reordering that cannot change the plan, and no migration or bulk write is involved |
| `cr-exec-prober` | the diff adds or changes **executable logic** (conditional, computation, data flow, callback, lifecycle hook), **or** includes a shell script or a CI workflow | the executable change is only markup, CSS, locale, a literal constant or a mechanical rename — no probe is possible |
| `cr-test-analyzer` | the diff adds or changes behavioral logic in application code (**with or without** tests in the diff) | the diff only touches views, assets or docs, or only renames without changing testable behavior |
| `cr-silent-failure-hunter` | the diff **adds** error handling (catch/rescue/except/recover, retry, fallback), or touches an external integration (HTTP, storage, queue, third-party API) | the diff's error handling is pre-existing and was only moved or reindented |
| `cr-comment-analyzer` | the diff adds or changes a comment, a docstring or technical prose | the diff's comments are trivial annotations (linter pragmas, encoding headers) |
| `cr-type-design` | the diff creates a **new class, struct, record or value object with state of its own** | the new type is a stateless procedural service, a thin job wrapper or a test helper |
| `cr-docs-guard` | the diff touches Markdown, a docs directory, or agent/skill/prompt definitions | — |

**If the RUNs exceed the bucket ceiling**, cut in this order (lowest marginal yield falls first): `cr-comment-analyzer` → `cr-type-design` → `cr-code-reviewer` → `cr-test-analyzer` → `cr-silent-failure-hunter` → `cr-exec-prober`. Never cut `cr-conventions`, `cr-boundary-guard`, `cr-docs-guard`, or `cr-data-layer` **when its trigger is a migration or a bulk write**. (`cr-data-layer` triggered purely by query cost is cuttable, right after `cr-exec-prober`.)

**If only non-cuttable lenses remain, the ceiling yields** — run them all.

In single mode the ceiling is an **attention budget, not a latency budget**: a cut lens is a pass you do not make, and there is no wave whose wall-clock it shortens. The trade is the same one, though — a lens run without attention is worse than a lens declared as a gap. **Every cut goes under *Verification gaps*, with the lens name and the reason.**

**Record the triage in the ledger** as two lists: **passes run** (lens + the trigger, one line each) and **passes skipped** (lens + the SKIP that matched, one line each). Silence about what did not run is indistinguishable from forgetting.

## Phase 2 — Diff map (one reading, every lens consumes it)

In the multi-agent pipeline each finder reread the diff from scratch; here you read it **once, carefully**, and the lenses consult the map. Read the full `git diff origin/$BASE...HEAD` (and whole files whenever a hunk does not explain itself) and record in the ledger:

- **Per file:** hunks and risk tags — `new-query`, `new-error-handling`, `migration`, `new-type`, `test`, `comment/prose`, `shell`, `bulk-write`, `external-integration`. The tags map 1:1 to the triage gates and become the index of your passes.
- **Deletion audit** (inherited from `cr-exec-prober`, done HERE because it requires the complete reading): for every line the diff REMOVES or replaces, name the invariant or behavior it guaranteed and where the new code re-establishes it. Not found = a candidate straight into the ledger (a guard removed, an error path lost, a validation narrowed, a deleted test that covered a real case). This is the class of bug a merge or rebase creates with no visible conflict.
- **Applicable convention docs** (`CLAUDE.md` / `AGENTS.md` at the root and in the touched directories, `CONTRIBUTING.md`, `docs/`) and the 2–4 lines of conventions that matter for this diff.

## Phase 3 — Lens passes (sequential, cheap → expensive)

For each active lens, **read `$LENS_DIR/<lens>.md` in full and apply its body as a checklist over the diff map** — including its own "Step 1", which is almost always "read what this project actually wrote before judging anything"; do it once and reuse the answer across the passes. Ignore only: the frontmatter (`tools:`, `model:`, the spawn-oriented description) and the **Report format** section, which the ledger replaces. **Do not distill or paraphrase the rules from memory** — the lens file is the source; if it changed, your pass changes with it.

Suggested order (textual first, execution last — probe questions accumulate for the batch):

1. `cr-docs-guard`, `cr-comment-analyzer` — mechanical judgment, fast
2. `cr-conventions`, `cr-code-reviewer` (if active), `cr-type-design`
3. `cr-boundary-guard`, `cr-silent-failure-hunter`, `cr-test-analyzer`
4. `cr-data-layer`, `cr-exec-prober` — the ones that generate the most probe questions

During the passes:

- **Grep, Read and `git diff -S` inline, freely** — they are cheap and immediate.
- **A check that requires booting the project's runtime or opening a database connection does NOT run now**: it becomes a numbered question under *Probe questions* in the ledger (`P<k> (C<n>): <what to run and what the output decides>`). On a project with an expensive boot, each start costs real time; in the multi-agent pipeline every agent paid its own — the gain of this architecture is paying **one** for all the lenses. Do not waste that gain by firing a one-off probe in the middle of a pass.
- A candidate is born in the ledger immediately (the Preparation format), including a `[CANDIDATE]` with no proof yet.
- What you checked and did **not** turn into a candidate goes under *Verified and dismissed* right away, with the reason.

**No transport budget:** `/cr`'s "8 findings / 6 lines" limit existed because a long subagent response died in delivery — here there is no intermediate delivery. Record what you find, in full.

**Sweep (only for diffs >400 lines):** at the end of the passes, reread the diff looking ONLY for what is not already in the ledger, focusing on what a first pass tends to miss: code moved or extracted that lost a guard or an anchor; asymmetric setup/teardown in tests; an inverted config default; a deleted line whose invariant nobody re-established. Running the sweep here, before the verify, is the single-agent advantage — in the multi-agent pipeline it required an extra round of verifiers.

## Phase 4 — Probe checkpoint (one boot answers everything)

Group ALL the accumulated questions and answer them in as few runs as possible:

- **One** read-only script for the project's runtime (its REPL, script runner or equivalent — find the command in `CLAUDE.md`, the README or the Makefile). Read-only means read-only: no create/update/delete/destroy, no migration, no writes. Prefer inspecting the generated query (the ORM's SQL-dump equivalent) over executing a mutation. The script file goes in the session scratchpad, **never in the repository**.
- **One** batched database session with every read-only query (SELECT / EXPLAIN / schema description), if the project exposes one.
- The project's test runner on a **focused** test, when the question is about a specific test.
- Shell script in the diff: a syntax check (`bash -n`) plus critical reading of the portability traps of the shell the project actually targets. **Do not execute a script that talks to the network or to a server.**

If no read-only execution path is discoverable, **do not invent one** — fall back to static analysis and put what you could not run under *Verification gaps*.

Record each output in the ledger next to its question, and update the **Rule/Evidence:** field of the candidates that depended on it.

## Phase 5 — Adversarial verify (the pass that replaces cr-verifier)

Now you switch sides: for every candidate that is **CRITICAL, HIGH, `[CANDIDATE]`, or carries a runtime claim**, the mission is to **REFUTE it**. The *Refutation attempt* field is mandatory — a CONFIRMED without one does not exist. The rules are `cr-verifier`'s (read `$LENS_DIR/cr-verifier.md` before this pass if you have not read it in this run):

- Follow the **real path of the value** (getters, callbacks, defaults, decorators) — do not judge a function in isolation; that is the number one false positive.
- A finding that depends on data uses a **real record** from a database you can read — a fabricated scenario neither proves nor refutes.
- A query-cost finding needs the real generated SQL plus an execution plan — an estimate does not count.
- A visual/CSS finding: the proof is the screen. With no app running, the maximum verdict is PLAUSIBLE plus the shortest manual check for the human.
- Suspected pre-existing: compare against `git show origin/$BASE:<file>` on the **same record** — never stash or checkout.
- **REFUTED only with constructible proof** (a real line cited, an impossibility demonstrated, a guard inside the diff itself, or a probe whose output contradicts it). **Do not refute as "speculative"** when the state is realistic: a concurrency race, a nil on a rare-but-reachable path, a zero-falsy treated as absent, an off-by-one on a boundary that is not excluded, a partial retry — that is PLAUSIBLE, not refuted.

Any new probe this pass requires: **batch it again** — a second runtime run at most, not one per candidate.

Verdicts (update **Status:** in the ledger, with the evidence in *Refutation attempt*):

- **CONFIRMED** — the triggering input/state and the wrong output are named, with the command and output (or the cited line) that proves it.
- **REFUTED** — drops out of the report; goes under *Verified and dismissed* with the proof (a refutation has preventive value — it stops the next round from reopening it).
- **PLAUSIBLE** — real mechanism, uncertain trigger: attach what would confirm it plus the shortest manual check.
- **PRE-EXISTING** — identical behavior on the default branch for the same record; its own section, a follow-up candidate.

**MEDIUM/LOW findings backed by a cited rule** do not go through execution-based refutation: check inline that the citation exists, that it comes from the reviewed project's own documents, and that it applies to that line — yes keeps it, no cuts it.

## Phase 6 — Report and comment

**Composition by reference:** the comment is assembled from the ledger **without rewriting its technical content** — title, problem, failure scenario and evidence go in as recorded (paraphrasing during synthesis introduces error). Your editing is selection, ordering (correctness before cleanup at the same severity) and formatting.

**Readability rules — the reader is a human scanning GitHub:**

1. **One finding = one numbered `####` heading**, with the title in plain language.
2. **Short visible layer:** location, problem (2–4 sentences in separate paragraphs), failure scenario and suggested fix. Target: ≤10 visible lines per finding.
3. **Verification evidence ALWAYS inside `<details>`**.
4. **Backticks only for real code** — prose in plain sentences.
5. **Index at the top:** a table of every finding (number, severity, title, location, verdict).
6. *Verified and dismissed* and *Pre-existing* go entirely inside `<details>`; *Verification gaps* stays visible.

Save the full report to `$OUT_DIR/cr_single_$PR_NUM.md` (a path distinct from `/cr`'s on purpose — running both skills on the same PR is the comparison scenario and they must not collide; header with PR/SHA/branch/timestamp/lenses run). Then post **ONE comment** on the PR (`gh pr comment $PR_NUM --body-file -`, body through a heredoc):

```markdown
## 🔍 Agentic code review (single agent) — PR #<PR_NUM>

**Lenses:** <passes run> · **Bucket:** <docs-only|trivial|surgical|feature>
**Not run:** <lens — the SKIP that matched; …>
**Scope reviewed:** <files/lines, where the logic lives>

### Index

| # | Sev | Finding | Where | Verdict |
|---|---|---|---|---|
| 1 | 🚨 | <short title> | `file:line` | CONFIRMED |
| 2 | ⚠️ | <short title> | `file:line` | PLAUSIBLE |

### 🚨 CRITICAL (<N>)

#### 1. <Plain-language title — what breaks, for whom>

[`file:line`](<link>) · **CONFIRMED** · lens <cr-*>

<The problem in 2–4 sentences, in short paragraphs separated by blank lines.>

**Failure scenario:** <concrete input/state → visible consequence>

**Suggested fix:** <1–2 sentences; a code snippet only if it fits in ≤5 lines>

<details>
<summary>🔬 Verification — how it was proven (and the refutation attempt)</summary>

<probe: command + relevant output, base-branch vs PR comparison, cited lines>

</details>

### ⚠️ HIGH (<N>) / 📝 MEDIUM (<N>) / 💡 LOW (<N>)

(same format, continuous numbering; empty sections are omitted; in MEDIUM/LOW the
<details> block is optional when the evidence is a one-line rule citation)

### ⚠️ Verification gaps (what the human reviewer needs to know)

- <what was not verified + the shortest manual check>
- <a lens cut by the bucket ceiling, if any>
- <no read-only execution path discoverable, if that was the case>

<details>
<summary>🔎 Pre-existing (<N>) — flagged, not fixed in this PR</summary>

- <real bug with identical behavior on the default branch; follow-up candidate>

</details>

<details>
<summary>🛑 Verified and dismissed (<N>) — do NOT reopen</summary>

- <refuted hypothesis + evidence, 1–2 lines each>

</details>

---

### Next steps for the author

1. **Apply the fixes that make sense** — review every change
2. **For findings you will NOT apply** — justify (false positive, out of scope, accepted trade-off)
3. **Reply on this PR**: applied (commits) / not applied (one line each)
4. **Request human review** after replying

---
<sub>🤖 Generated by [/cr-single](https://github.com/MarceloCajueiro/agentic-cr) (single-agent variant)</sub>
```

If the repository's PRs and comments are predominantly written in a language other than English, write the comment in that language, keeping the structure.

**Close the phase by checking branch, SHA and tree:**

```bash
git status -sb | head -1 && git rev-parse HEAD && git status --porcelain
```

A branch or SHA different from the recorded one, or a dirty tree: you broke principle 1 somewhere — revert it before going on and record it in the report. Do not trust `git push` here either: on the wrong branch it answers "Everything up-to-date" while the PR stays behind.

## Phase 7 — Fix pass (inline, this session) — ONLY with `--fix`

**This phase runs only when the invocation carried `--fix`.** Without it the pipeline ends at phase 6: the comment is posted, nothing is edited, nothing is committed, nothing is pushed, and you report to the user that the review is done and the fixes are the PR owner's call. Do not offer to apply them anyway — the whole point of the flag is that touching someone's branch is their decision. `/cr-single --fix` is how they make it.

**The only point in the cycle where code changes.** Only with the comment already posted. Decide **finding by finding** — do not apply in bulk, do not dismiss in bulk:

- **CRITICAL/HIGH:** apply, unless proven a false positive. Every fix gets (or reuses) a test.
- **MEDIUM/LOW:** apply when the cost is low and the gain is real. Decline what is out of scope or speculative — saying why.
- Run the project's test suite (find the command in the repository's `CLAUDE.md`, README, Makefile, `package.json`). Commits follow the repository's own conventions, including language: `fix: apply code review findings from PR #<PR_NUM> (<short summary>)`. Push to the PR branch.
- **Confirm the push landed** by comparing the local head with `gh pr view <PR_NUM> --json headRefOid -q .headRefOid` — "Everything up-to-date" is also the answer you get on the wrong branch.

Reply on the PR with **Applied** (commits) / **Not applied** (one-line justification each) / test suite status. Human review proceeds as usual afterwards.
