# agentic-cr

Agentic code review for GitHub pull requests - **the diff decides which lenses run, every lens is read-only, every serious candidate gets refuted before it reaches the author.**

`/cr` triages the PR diff, applies the review lenses the diff justifies, verifies every CRITICAL/HIGH and every unproven claim by execution, and posts a single scannable comment on the PR - with the confirmed findings, the refuted ones (so the next round does not reopen them), and an explicit list of what was **not** verified. It stops there: applying the findings is the PR owner's call. Run `/cr --fix` to walk them one by one, applying what is real and declining what is not.

Everything runs **in one agent, sequentially** - no subagents, no `Workflow`, no fan-out - so it runs on any harness that can run `git`, `bash` and `gh`: pi, Claude Code, Codex, Cursor, Gemini CLI and every other Agent Skills host. It installs with `npx skills add`, the same way as any other skill. There is no plugin and no harness-specific setup.

Nothing in it is tied to a language, a framework or a repository: each lens reads the reviewed project's own conventions before judging anything.

- 🎯 **Triage before the passes** - a lens with nothing to do on this diff does not run, and the skip is reported
- 🔬 **Refutation by execution** - a mandatory *Refutation attempt* per finding; no CONFIRMED without a probe whose output decides
- 🚫 **No invented rules** - a citation must come from the reviewed project's own docs, or the finding stands on evidence alone
- 🔒 **Read-only by default** - nothing is edited, committed or pushed unless you pass `--fix`
- 📢 **Declared coverage** - cut lenses, unmeasurable claims and missing runtimes go under *Verification gaps*
- 📦 **Any repo, any harness** - no project-specific configuration; `gh` infers the repository from the git remote
- 🗂️ **Disk ledger** - a finding is written the moment it is born; the comment is assembled from the file, never from memory
- 🧩 **One install method** - `npx skills add`, no plugin, no harness lock-in

---

## How it works

```
          triage         diff map       lens passes      probe       verify        comment
PR ───►  (bucket)  ───►  (one read)  ─►  (sequential) ─► (batched) ─► (refute) ─► (one PR comment) ─► fix pass (--fix only)
```

1. **Triage** - the diff is bucketed (docs-only / trivial / surgical / feature), which sets a ceiling on how many lenses run, and each lens passes an explicit RUN/SKIP gate. Both lists - run and skipped, with the reason - end up in the comment.
2. **Diff map** - the diff is read **once, carefully**, and mapped: per-file hunks and risk tags, the applicable convention docs, and a deletion audit for every line the diff removes or replaces (the class of bug a merge or rebase creates with no visible conflict).
3. **Lens passes** - the active lenses are read in full from `references/lenses/` and applied as checklists over the map, cheapest first, execution-heavy last. A candidate goes into the ledger the moment it is born.
4. **Probe checkpoint** - every question that needs the project's runtime or a database is accumulated and answered in **one batched, read-only run**, not one boot per lens.
5. **Adversarial verify** - for every CRITICAL/HIGH, every unproven `[CANDIDATE]` and every runtime claim, the posture flips: the mission is to **refute it**, and the *Refutation attempt* field is mandatory. Verdicts: CONFIRMED, REFUTED, PLAUSIBLE or PRE_EXISTING.
6. **Comment** - one comment: an index table, one heading per finding, verification evidence folded into `<details>`, plus *Verification gaps*, *Pre-existing* and *Verified and dismissed*.
7. **Fix pass - only with `--fix`** - without the flag the pipeline stops at the comment and the fixes are the PR owner's call. With it, the session decides finding by finding: CRITICAL/HIGH applied unless proven a false positive (each with a test), MEDIUM/LOW applied when cheap and real, declined with a stated reason otherwise. Suite runs, commits pushed, summary replied on the PR.

---

## The lenses

| Lens | Covers |
|---|---|
| `cr-boundary-guard` | The project's declared critical dimension - data isolation, authorization, authentication, schema traps. Falls back to a generic access-control floor when the project declares nothing. |
| `cr-conventions` | The project's own written conventions, and APIs newer than the pinned runtime and dependencies. Base lens of every code PR. |
| `cr-exec-prober` | Runs the changed code with read-only probes; audits deleted lines for lost invariants; shell scripts and CI workflows. |
| `cr-data-layer` | Measured query cost (execution plans, not estimates), migrations, and bulk writes that bypass the model layer. |
| `cr-test-analyzer` | Coverage gaps and, above all, tests with no power to fail. |
| `cr-silent-failure-hunter` | Swallowed errors, broad catches, fallbacks that mask problems. |
| `cr-type-design` | Invariants, encapsulation and enforcement of new types. |
| `cr-comment-analyzer` | Comment accuracy against the real code; comment rot. |
| `cr-docs-guard` | Docs that assert what is no longer true; broken paths, links and commands; agent/prompt files that break their own pipeline. |
| `cr-code-reviewer` | Generalist sweep on feature-sized PRs, filtered at confidence ≥ 80. |
| `cr-verifier` | The rules of adversarial verification, applied in phase 5 - the one lens that never finds anything, only judges. |

The definitions are **canonical in `skills/cr/references/lenses/`**, inside the skill: a skill installer copies the skill directory and nothing outside it, so a lens file has to live there to survive installation. `scripts/lens-dir.sh` resolves that directory at runtime.

Five of them (`cr-code-reviewer`, `cr-comment-analyzer`, `cr-silent-failure-hunter`, `cr-test-analyzer`,
`cr-type-design`) are generalized adaptations of the agents in Anthropic's
[`pr-review-toolkit`](https://github.com/anthropics/claude-code/tree/main/plugins/pr-review-toolkit) (MIT),
with the provenance recorded in each file.

---

## Requirements

- [GitHub CLI](https://cli.github.com) (`gh`) authenticated with access to the repo
- `git` and `bash`
- A clean working tree on the PR branch

That is the whole list. No subagent support, no plugin, no runtime to boot for the review itself.

---

## Install

### Any Agent Skills harness (pi, Claude Code, Codex, Cursor, Gemini CLI and ~75 more)

```bash
npx skills add MarceloCajueiro/agentic-cr          # interactive
npx skills add MarceloCajueiro/agentic-cr --list   # what is in the repo
npx skills add MarceloCajueiro/agentic-cr -g -a pi # global, pi only
```

The [skills.sh](https://skills.sh) CLI installs into the right directory for each harness (`.pi/skills/`,
`.claude/skills/`, `.agents/skills/`, …). It copies the **whole skill directory**, so `/cr` carries its
lens definitions and its `lens-dir.sh` resolver with it, and there is nothing else to install. Invoke it as
`/cr` in Claude Code, `/skill:cr` in pi.

### Manual

```bash
git clone https://github.com/MarceloCajueiro/agentic-cr
cp -r agentic-cr/skills/cr ~/.agents/skills/   # or .pi/skills, .claude/skills, ...
```

---

## Usage

From a checkout of the repo whose PR you want reviewed:

```
/cr           # reviews the PR of the current branch
/cr 123       # reviews PR #123
/cr --fix     # reviews, then applies the findings and pushes
/cr 123 --fix # same, on PR #123
```

**Review only by default.** Without `--fix` the pipeline never edits, commits or pushes - it posts the
comment and stops. Applying the findings is the PR owner's decision; `--fix` is how they delegate it.

The full report is written to `/tmp/cr/<owner>-<repo>/cr_<PR>.md` - the audit artifact, with no verbosity
limit. The PR gets the readable version.

---

## Why one agent

A subagent fan-out costs something: each finder reboots the project's runtime, rereads the diff from scratch,
and pays a response-transport budget (the "8 findings / 6 lines" cap exists because an over-long subagent
answer dies in delivery). It is also the reason such a pipeline only runs on a harness with subagents.

This one puts everything in one context and compensates structurally for what the fan-out gives for free:

| What a fan-out gives for free | How this pipeline replaces it |
|---|---|
| An independent verifier | Refutation **by execution**: a mandatory *Refutation attempt* field per finding; no CONFIRMED without a probe whose output decides |
| A second lens catching what the first dropped | `[CANDIDATE]` posture - liberal in the find, rigorous only in the verify |
| Isolated read-only agents | Read-only as **discipline**: writes allowed only under `/tmp/cr/...` and the scratchpad, checked against `git status` at the close |
| Context that cannot be summarized away | A **disk ledger** appended the moment a finding is born; the comment is assembled from the file, never from memory |

What it gains: one runtime boot answers every lens's probes (the *probe checkpoint*), one careful reading of
the diff feeds all the passes (the *diff map*, which is also where the deletion audit happens), the sweep runs
before the verify instead of requiring an extra verifier round, and there is no transport budget, so findings
are recorded in full.

---

## Design rules

These are the rules the pipeline holds itself to, and the reason it produces fewer false positives than a
single-pass review:

1. **Review does not edit, the fix pass does not review.** No code changes between the first pass and the
   posted comment - every pass must see the same diff. A diff that shifts mid-cycle produces phantom
   findings and a comment pointing at lines that no longer exist.
2. **A finding requires a citable rule OR executable evidence** - and the rule must be one the reviewed
   project actually wrote. A fabricated citation is worse than a missed finding.
3. **A runtime claim only enters CONFIRMED by execution.** Static reading describes the path as written.
4. **Partial coverage is declared, never silent.** A cut lens, an unmeasurable cost, an undiscoverable test
   command - all of it goes under *Verification gaps* in the comment.
5. **A lens with nothing to do does not run.** An idle pass costs the same attention as a working one and
   returns noise.

### Severity scheme

| Severity | Meaning |
|---|---|
| 🚨 CRITICAL | Production, security or data-integrity bug - injection, auth bypass, data leak across a boundary, data loss, destructive migration |
| ⚠️ HIGH | High incident probability - query in a loop on a hot path, race condition, unhandled error, missing tests for new logic |
| 📝 MEDIUM | Quality issue that becomes tech debt - refactor suggestions, oversized functions, context-free logging |
| 💡 LOW | Style and nits |

### Verdicts

| Verdict | Meaning |
|---|---|
| CONFIRMED | The verifier named the input and the wrong output, with proof |
| PLAUSIBLE | Real mechanism, uncertain trigger - enters with the shortest manual check attached |
| REFUTED | Constructively disproven - recorded in the comment so the next round does not reopen it |
| PRE_EXISTING | Real bug, identical on the default branch - flagged as a follow-up, not as a finding of this PR |

---

## Notes

- Comments are written in English by default; if a repo's PRs are predominantly in another language, the pipeline follows suit.
- Version 3.0.0 collapsed the two skills into one. `/cr` is now the sequential, harness-agnostic pipeline (the old `/cr-single`, renamed) and the subagent fan-out was removed, so the repo has no `.claude-plugin` and no `agents/` directory. **If you installed it as a Claude Code plugin, uninstall it** (`/plugin uninstall agentic-cr@cajueiro-plugins`) and install the skill instead: `npx skills add MarceloCajueiro/agentic-cr`.
- Version 2.2.0 made both skills installable by any Agent Skills harness (`npx skills add MarceloCajueiro/agentic-cr`).
- Version 2.1.0 added `/cr-single`, the sequential variant, so the two architectures could be compared on the same PR. Version 3.0.0 kept that architecture and dropped the other.
- Version 2.0.0 replaced the previous architecture (two outsourced review passes, `/cr-1`, `/cr-2`, `/cr-consolidate`) with this lens team. Those commands no longer exist.

---

## License

MIT © Marcelo Cajueiro - [cajueiro.tech](https://cajueiro.tech)
