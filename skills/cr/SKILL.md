---
name: cr
description: Agentic code review pipeline for a GitHub PR — triages the diff to decide which review lenses run, fans them out in parallel as read-only finder agents, refutes their candidates with an adversarial verifier, and posts one consolidated comment on the PR. Read-only by default; with --fix it also runs a finding-by-finding fix pass. Use when the user wants a PR reviewed end to end, says "/cr", "review this PR", or "run the code review pipeline".
argument-hint: "[PR-number] [--fix] (default: PR of the current branch, review only)"
user_invocable: true
---

# /cr — agentic code review

`$ARGUMENTS` holds the PR number and/or the `--fix` flag, in any order — `/cr`, `/cr 123`,
`/cr --fix`, `/cr 123 --fix` are all valid. Strip the flag before resolving the number:

```bash
FIX=0; case " $ARGUMENTS " in *" --fix "*) FIX=1;; esac
PR_ARG="$(printf '%s' "$ARGUMENTS" | sed 's/--fix//g' | tr -d '[:space:]')"
PR_NUM="${PR_ARG:-$(gh pr view --json number -q .number)}"
```

No PR for the branch: stop and tell the user.

**`--fix` is the only thing that authorizes phase 5.** Without it this command reviews and comments; it never edits, commits or pushes. Carry `FIX` to the end — phase 5 checks it.

Everything runs against the repository of the current working directory — `gh` infers it from the git remote, so **never pass `-R`**. Resolve the default branch once and use it everywhere a base is needed:

```bash
BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner | tr '/' '-')
OUT_DIR="/tmp/cr/$REPO_SLUG"; mkdir -p "$OUT_DIR"
```

**Principles (they hold across the whole pipeline):**

1. **Review does not edit, the fix pass does not review.** No code change between spawning the first agent and posting the comment — every agent must see the same diff.
2. **A finding requires a citable rule OR executable evidence.** With neither, it does not enter. And the rule must be one the *reviewed project* actually wrote — a fabricated citation is worse than a missed finding.
3. **A runtime claim only enters CONFIRMED by execution.** Static reading describes the path as written; execution shows what actually happens.
4. **Partial coverage is declared, never silent** — what was not verified goes under *Verification gaps*.
5. **A lens with nothing to do on this diff does not run.** An agent spawned with no target costs the same wall-clock as one with a target and returns noise — the triage justifies every spawn AND every skip.

## Resolving agent names

The lenses ship with this plugin as agent types. Installed as a plugin they are listed as `agentic-cr:cr-verifier`, `agentic-cr:cr-conventions` and so on; running from a local checkout they may be listed under the bare name (`cr-verifier`). **Check the available agent types once at the start** and use whichever form is listed — prefixed first, bare as fallback. Use that same form in every `agentType` below.

## Preparation

Precondition: **clean working tree** (`git status --porcelain` empty). Record the branch and SHA — they are what you check against at the end of every phase:

```bash
git rev-parse --abbrev-ref HEAD && git rev-parse HEAD
```

You are normally already on the PR branch: the diff is on disk (`git diff origin/$BASE...HEAD`) and nobody checks anything out. The agents get that instruction in their prompt and you verify it at the end.

## Phase 1 — Triage: who reviews this PR, and who does not

Decide from the **final diff**, not from the branch history. Collect the signals in one go:

```bash
gh pr diff "$PR_NUM" --name-only
git diff --stat "origin/$BASE...HEAD"
git diff --unified=0 "origin/$BASE...HEAD" | grep -E '^\+' | grep -cEi 'rescue|except|catch|recover|ensure|finally'   # error handling signal
git diff --unified=0 "origin/$BASE...HEAD" | grep -E '^\+' | grep -cE '^\+\s*(class|struct|record|interface|type) '  # new type signal
```

### Buckets (they set the ceiling on how many finders run)

| Bucket | Condition | Finder ceiling |
|---|---|---|
| 📄 **docs-only** | every file is Markdown, docs or agent/prompt definitions — **no** executable file | 1–2 |
| 🔹 **trivial** | lockfile or version bump, or ≤10 lines in 1 file | 2 |
| 🔸 **surgical** | ≤ ~40 lines, ≤ 3 files | **≤ 4** |
| 🔶 **feature** | anything larger | **≤ 7** (+ sweep if >400 lines) |

**Hard rule (it precedes the docs gate):** any executable file in the diff — a shell script, a CI workflow, a migration, a template that runs, or any source file — **forbids** docs-only treatment. A PR that looks like docs can carry its Critical inside the one `.sh` nobody read.

### Per-lens gates — SPAWN if, SKIP if

The SKIP predicate binds as hard as the SPAWN one: if SKIP matches, the lens **does not run** even when SPAWN also matches (SKIP is the more specific exception).

| Agent | SPAWN if | SKIP if |
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

**If the SPAWNs exceed the bucket ceiling**, cut in this order (lowest marginal yield falls first): `cr-comment-analyzer` → `cr-type-design` → `cr-code-reviewer` → `cr-test-analyzer` → `cr-silent-failure-hunter` → `cr-exec-prober`. Never cut `cr-conventions` (the base lens: it spawns unconditionally on any PR with code), `cr-boundary-guard`, `cr-docs-guard`, or `cr-data-layer` **when its trigger is a migration or a bulk write** — each covers a class of risk no other lens sees. (`cr-data-layer` triggered purely by query cost is cuttable, right after `cr-exec-prober`.)

**If only non-cuttable lenses remain, the ceiling yields** — run them all. The ceiling is a latency budget, not a safety switch: cutting the Critical lens to fit in four trades time for Critical risk, which is the wrong trade. The overflow goes under *Verification gaps* like any other cut.

**Every cut goes under *Verification gaps*, with the lens name and the reason** — both the cut foreseen by the order above and a consented overflow. A cut that never appears in the comment is coverage lost in silence.

**Cost and latency per lens** — the wave ends when the slowest agent ends, so the mix matters more than the count:

- The expensive lenses are the ones that boot the project's runtime (`cr-exec-prober`, `cr-data-layer`, `cr-verifier`). Their prompts already tell them to group every check into a single boot; a project with a slow boot pays that cost once per agent.
- Purely textual lenses (`cr-docs-guard`, `cr-comment-analyzer`) run with `model: 'sonnet'` and `effort: 'low'` — their judgment is mechanical.

**Record the triage** (it goes in the comment) as two lists: **spawned** (agent + the trigger, one line each) **and not spawned** (agent + the SKIP that matched, one line each). Silence about what did not run is indistinguishable from forgetting.

**Build the scope block** — the same one for every agent in this run (finders, verifiers and sweep all get identical context):

```markdown
## Review scope
Diff: git diff origin/<BASE>...HEAD   (PR #<PR_NUM>, head <SHA>, branch <BRANCH>)
Changed files (<n>): <list>
Applicable convention docs: <root CLAUDE.md/AGENTS.md + the ones covering touched directories>

## What changed
<one-paragraph summary>

## Relevant conventions
<2-4 lines: what in the applicable docs matters for this diff>
```

## Phase 2 — Finder wave + verify (via the Workflow tool, from the surgical bucket up)

**The docs-only and trivial buckets (1–2 finders) do NOT use Workflow** — building a script, running it in the background and waiting for a notification costs more than the fan-out it orchestrates. Spawn those finders directly with the Agent tool, in a single block of tool calls, and go to phase 3. Workflow pays for itself from the surgical bucket up.

In the other buckets, **this phase runs through the `Workflow` tool** — invoking it here is part of this command's definition, so the opt-in for multi-agent orchestration is already given; do not ask the user. Why Workflow instead of a manual fan-out: the agents' output stays out of your context, dedup→verify becomes a deterministic pipeline instead of your judgment on every round, and retrying a dead agent is code rather than improvisation.

> **Fallback:** with no `Workflow` tool available in the session, spawn the triaged finders in **a single block of tool calls** through the Agent tool and run dedup/verify by hand under the same rules as phase 3. Same result, different mechanics.

Build the script from the template below, replacing only the `FINDERS` list (from phase 1) and passing the scope block through `args`:

```javascript
export const meta = {
  name: 'agentic-cr',
  description: 'Agentic code review: lenses in parallel, dedup, adversarial verify',
  phases: [
    { title: 'Find', detail: 'triaged lenses in parallel, read-only' },
    { title: 'Verify', detail: 'cr-verifier per location group' },
    { title: 'Sweep', detail: 'only for PRs >400 lines: gaps-only' },
  ],
}

// ── fill in from phase 1; use the agent-name form the session actually lists ──
const FINDERS = [
  { type: 'agentic-cr:cr-boundary-guard' },
  { type: 'agentic-cr:cr-conventions' },
  { type: 'agentic-cr:cr-exec-prober' },
  // { type: 'agentic-cr:cr-docs-guard', model: 'sonnet', effort: 'low' },
]
const VERIFIER = 'agentic-cr:cr-verifier'
const SWEEPER = 'agentic-cr:cr-code-reviewer'
const SWEEP = false   // true when the diff is larger than 400 lines

const SCOPE = args.scope          // the scope block from phase 1
const RECALL = `You are ALREADY on the PR branch: do NOT check out, do NOT create a branch, do NOT run stash/reset/clean, do NOT edit any file in the repository. Investigate beyond the diff (whole files, callers, dependencies). Follow your agent definition to the letter, including the finding format and the "Verified and dismissed" section.

Recall posture: a bug candidate with a nameable failure scenario goes into the report EVEN without complete proof, marked [CANDIDATE] — an independent verifier judges it next; do not silently drop the half-believed. The "citable rule OR evidence" bar applies to the pipeline's final report, not to your candidate list. A failure scenario is the visible consequence (an error, wrong output, lost data), not an intermediate state ("the value goes stale").

If you need a probe: group ALL checks into a single run of the project's runtime. On a project with an expensive boot, every extra start costs the whole wave wall-clock time. If no read-only execution path is discoverable, do not invent one — fall back to static analysis and say what you could not run.

Output budget: at most 8 findings, each in up to 6 lines. Cite \`file:line\` and summarize — do not paste large excerpts or reproduce whole tables. An over-long response dies mid-delivery and the whole lens is lost; six lean findings beat twelve that never arrive.`

const FINDINGS = {
  type: 'object',
  required: ['findings', 'verified_and_dismissed'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'file', 'line', 'title', 'problem', 'failure_scenario'],
        properties: {
          severity: { enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          file: { type: 'string' }, line: { type: 'integer' },
          title: { type: 'string' }, problem: { type: 'string' },
          failure_scenario: { type: 'string' }, suggested_fix: { type: 'string' },
          candidate: { type: 'boolean' },       // true = [CANDIDATE], not proven
          runtime_claim: { type: 'boolean' },   // runtime assertion with no probe
          evidence: { type: 'string' },         // probe output or rule citation
          rule_citation: { type: 'string' },
        },
      },
    },
    verified_and_dismissed: { type: 'array', items: { type: 'string' } },
    coverage_gaps: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT = {
  type: 'object',
  required: ['verdicts'],
  properties: {
    verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['index', 'verdict', 'evidence'],
        properties: {
          index: { type: 'integer' },
          verdict: { enum: ['CONFIRMED', 'REFUTED', 'PLAUSIBLE', 'PRE_EXISTING'] },
          evidence: { type: 'string' },
          manual_check: { type: 'string' },   // PLAUSIBLE only: the shortest check
        },
      },
    },
  },
}

// ── Find phase: one lens per agent, all in parallel ──
phase('Find')
const reports = await parallel(FINDERS.map(f => () =>
  agent(`${SCOPE}\n\n${RECALL}`, {
    agentType: f.type, label: f.type, phase: 'Find', schema: FINDINGS,
    ...(f.model ? { model: f.model } : {}), ...(f.effort ? { effort: f.effort } : {}),
  })
  // agent() returns null on terminal death: one second chance, then it becomes a provenance note
  .then(r => r ?? agent(`${SCOPE}\n\n${RECALL}`, {
    agentType: f.type, label: `${f.type}:retry`, phase: 'Find', schema: FINDINGS,
    ...(f.model ? { model: f.model } : {}), ...(f.effort ? { effort: f.effort } : {}),
  }))
  .then(r => ({ type: f.type, report: r }))
))

const alive = reports.filter(r => r && r.report)
const dead = FINDERS.map(f => f.type).filter(t => !alive.some(a => a.type === t))
log(`finders: ${alive.length}/${FINDERS.length} responded${dead.length ? ` — no verdict from: ${dead.join(', ')}` : ''}`)

// ── Justified barrier: dedup needs ALL candidates before spending a verifier ──
const all = alive.flatMap(a => (a.report.findings || []).map(f => ({ ...f, detected_by: a.type })))
const groups = {}
for (const f of all) {
  // location group: same file, line within ±3
  const key = Object.keys(groups).find(k => {
    const g = groups[k]
    return g[0].file === f.file && Math.abs(g[0].line - f.line) <= 3
  }) || `${f.file}:${f.line}`
  ;(groups[key] = groups[key] || []).push(f)
}
// only a group holding a CRITICAL/HIGH, a [CANDIDATE] or an unproven runtime claim goes to verify
const needsVerify = Object.entries(groups).filter(([, g]) =>
  g.some(f => f.severity === 'CRITICAL' || f.severity === 'HIGH' || f.candidate || f.runtime_claim))
log(`${all.length} candidates → ${Object.keys(groups).length} groups → ${needsVerify.length} to verify`)

// ── Verify phase: one cr-verifier per group, judging each candidate by index ──
phase('Verify')
const verdicts = await parallel(needsVerify.map(([key, g]) => () =>
  agent(`${SCOPE}

Refute each candidate below INDEPENDENTLY, by index — candidates on the same line may be distinct problems. Judge by the real path of the value, with real data, not by how plausible the narrative sounds.

${g.map((f, i) => `[${i}] ${f.severity} ${f.file}:${f.line} — ${f.title}
Problem: ${f.problem}
Failure scenario: ${f.failure_scenario}
Finder's evidence: ${f.evidence || '(none)'}`).join('\n\n')}`,
    { agentType: VERIFIER, label: `verify:${key}`, phase: 'Verify', schema: VERDICT })
    .then(v => ({ key, group: g, verdicts: v && v.verdicts }))
))

// ── Sweep phase: large PRs only, gaps-only ──
let sweep = null
if (SWEEP) {
  phase('Sweep')
  sweep = await agent(`${SCOPE}

The following has already been found:
${all.map(f => `- ${f.file}:${f.line} — ${f.title}`).join('\n') || '(nothing)'}

Reread the diff and the functions around it looking ONLY for defects that are NOT on that list. Focus on what a first pass tends to miss: code moved or extracted that lost a guard or an anchor; asymmetric setup/teardown in tests; an inverted config default; a DELETED line whose invariant nobody re-established. Up to 8 new candidates; if there is nothing, return an empty list — do not pad.

${RECALL}`, { agentType: SWEEPER, label: 'sweep', phase: 'Sweep', schema: FINDINGS })
}

return {
  groups, verdicts: verdicts.filter(Boolean), sweep,
  dead_agents: dead,
  dismissed: alive.flatMap(a => a.report.verified_and_dismissed || []),
  gaps: alive.flatMap(a => a.report.coverage_gaps || []),
}
```

Workflow runs in the **background**: it returns a task ID immediately and the result arrives later as a task notification. Wait for it — do not re-invoke in the meantime. If the return comes back empty or odd, **read `<transcriptDir>/journal.jsonl` before diagnosing** — it records what each agent actually returned.

**Sweep candidates** (when there are any) go through the same verify — summarize them in session and spawn the missing `cr-verifier` agents, or re-invoke the Workflow with `resumeFromRunId` and the sweep already inside the verify fan-out.

## Phase 3 — Apply the verdicts

The script already did the grouping and the verify; what is left is your judgment:

1. **An exact duplicate** (same problem, same core verb + object) inside a group becomes ONE entry with `**Detected by:** <agents>` — two independent lenses landing on the same point is a confirmation signal, record it.
2. **MEDIUM/LOW findings that are neither candidates nor runtime claims, and are not grouped with a CRITICAL/HIGH**, never reached a verifier (the script does not send them): check those yourself inline — does the citation exist, is it from the reviewed project's own documents, and does it apply to that line? Keep it if so, cut it if not.
3. Apply the verdicts: **REFUTED** drops out (into *Verified and dismissed*, including refutations with preventive value — they stop the next round from reopening them); **CONFIRMED** enters with its evidence; **PLAUSIBLE** enters marked, with the manual check attached; **PRE_EXISTING** goes to its own section. **A candidate with no verdict** (`dead_agents`, or a verifier that died) **drops** with a provenance note — it never enters as a fabricated PLAUSIBLE.

## Phase 4 — Report and comment

**Composition by reference:** the comment is assembled from the verified findings **without rewriting their technical content** — the `title`, `problem`, `failure_scenario` and `evidence` fields go in as the agents produced them (paraphrasing during synthesis introduces error). Your editing is selection, ordering (correctness before cleanup at the same severity) and formatting.

**Readability rules — the reader is a human scanning GitHub:**

1. **One finding = one numbered `####` heading**, with the title in plain language (the line that gets scanned). Never a single bullet with everything crammed inside.
2. **Short visible layer:** location, problem (2–4 sentences in separate paragraphs), failure scenario and suggested fix. Target: ≤10 visible lines per finding.
3. **Verification evidence ALWAYS inside `<details>`** — probe, output, ref comparison, counts. Whoever trusts the verdict does not need to open it; whoever doubts, opens it.
4. **Backticks only for real code** (an identifier, a selector, a command). Prose with a backtick every three words becomes a wall — write the explanation in plain sentences.
5. **Index at the top:** a table of every finding (number, severity, title, location, verdict) — the author decides where to start without scrolling the whole comment.
6. Long auxiliary sections (*Verified and dismissed*, *Pre-existing*) go entirely inside `<details>`; *Verification gaps* and *Provenance notes* stay visible (they are actionable and they affect confidence).

Save the full report to `$OUT_DIR/cr_$PR_NUM.md` (overwrite completely; header with PR/SHA/branch/timestamp/spawned agents) — that is the audit artifact, with no verbosity limit. Then post **ONE comment** on the PR (`gh pr comment $PR_NUM --body-file -`, body through a heredoc):

```markdown
## 🔍 Agentic code review — PR #<PR_NUM>

**Lenses:** <spawned agents> · **Bucket:** <docs-only|trivial|surgical|feature>
**Not spawned:** <agent — the SKIP that matched; …>
**Scope reviewed:** <files/lines, where the logic lives>

### Index

| # | Sev | Finding | Where | Verdict |
|---|---|---|---|---|
| 1 | 🚨 | <short title> | `file:line` | CONFIRMED |
| 2 | ⚠️ | <short title> | `file:line` | PLAUSIBLE |

### 🚨 CRITICAL (<N>)

#### 1. <Plain-language title — what breaks, for whom>

[`file:line`](<link>) · **CONFIRMED** · detected by <agents>

<The problem in 2–4 sentences, in short paragraphs separated by blank lines.
Plain prose; backticks only for a real identifier or command.>

**Failure scenario:** <concrete input/state → visible consequence, 1–2 sentences>

**Suggested fix:** <1–2 sentences; a code snippet only if it fits in ≤5 lines>

<details>
<summary>🔬 Verification — how it was proven</summary>

<probe: command + relevant output, base-branch vs PR comparison, cited lines —
verbosity is welcome here>

</details>

### ⚠️ HIGH (<N>) / 📝 MEDIUM (<N>) / 💡 LOW (<N>)

(same format, continuous numbering; empty sections are omitted; in MEDIUM/LOW the
<details> block is optional when the evidence is a one-line rule citation)

### ⚠️ Verification gaps (what the human reviewer needs to know)

- <what was not verified + the shortest manual check>
- <a lens cut by the bucket ceiling, if any>
- <no read-only execution path discoverable, if that was the case>

### 📋 Provenance notes

- <only if an agent failed or was replaced>

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
<sub>🤖 Generated by [/cr](https://github.com/MarceloCajueiro/agentic-cr)</sub>
```

If the repository's PRs and comments are predominantly written in a language other than English, write the comment in that language, keeping the structure.

**Close the phase by checking branch, SHA and tree:**

```bash
git status -sb | head -1 && git rev-parse HEAD && git status --porcelain
```

A different branch or SHA means an agent moved you — go back (`git checkout <PR branch>`). A dirty tree means an agent wrote to the repository despite its instructions — revert it and record it under *Provenance notes*. Do not trust `git push` here either: on the wrong branch it answers "Everything up-to-date" while the PR stays behind.

## Phase 5 — Fix pass (inline, this session) — ONLY with `--fix`

**This phase runs only when the invocation carried `--fix`.** Without it the pipeline ends at phase 4: the comment is posted, nothing is edited, nothing is committed, nothing is pushed, and you report to the user that the review is done and the fixes are the PR owner's call. Do not offer to apply them anyway — the whole point of the flag is that touching someone's branch is their decision, not yours. `/cr --fix` is how they make it.

**The only point in the cycle where code changes.** Only with the comment already posted. Decide **finding by finding** — do not apply in bulk, do not dismiss in bulk:

- **CRITICAL/HIGH:** apply, unless proven a false positive. Every fix gets (or reuses) a test.
- **MEDIUM/LOW:** apply when the cost is low and the gain is real. Decline what is out of scope or speculative — saying why.
- Run the project's test suite (find the command in the repository's `CLAUDE.md`, README, Makefile, `package.json`). Commits follow the repository's own conventions, including language: `fix: apply code review findings from PR #<PR_NUM> (<short summary>)`. Push to the PR branch.
- **Confirm the push landed** by comparing the local head with `gh pr view <PR_NUM> --json headRefOid -q .headRefOid` — "Everything up-to-date" is also the answer you get on the wrong branch.

Reply on the PR with **Applied** (commits) / **Not applied** (one-line justification each) / test suite status. Human review proceeds as usual afterwards.
