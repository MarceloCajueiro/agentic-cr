# agentic-cr

Agentic code review for GitHub pull requests — **the diff decides which lenses run, every lens is read-only, every serious candidate gets refuted before it reaches the author.**

`/cr` triages the PR diff, fans out a team of specialized [Claude Code](https://docs.claude.com/en/docs/claude-code)
review agents in parallel, sends every CRITICAL/HIGH and every unproven claim to an adversarial verifier
that tries to *refute* it, and posts a single scannable comment on the PR — with the confirmed findings,
the refuted ones (so the next round does not reopen them), and an explicit list of what was **not** verified.
Then the main session walks the findings one by one, applying what is real and declining what is not.

Nothing in it is tied to a language, a framework or a repository: each lens reads the reviewed project's
own conventions before judging anything.

- 🎯 **Triage before spawn** — a lens with nothing to do on this diff does not run, and the skip is reported
- 🔬 **Adversarial verify** — findings are attacked before publication: CONFIRMED, REFUTED, PLAUSIBLE or PRE-EXISTING
- 🚫 **No invented rules** — a citation must come from the reviewed project's own docs, or the finding stands on evidence alone
- 🔒 **Read-only until the fix pass** — no file changes between the first agent and the posted comment
- 📢 **Declared coverage** — cut lenses, unmeasurable claims and missing runtimes go under *Verification gaps*
- 📦 **Any repo** — no project-specific configuration; `gh` infers the repository from the git remote

---

## How it works

```
                  ┌─ cr-boundary-guard ──┐
PR ──► triage ──► ├─ cr-conventions ─────┤ ──► dedup ──► cr-verifier ──► one PR comment ──► fix pass
       (bucket)   ├─ cr-exec-prober ─────┤   (±3 lines)  (refute each)     (index + gaps)     (inline)
                  └─ … the lenses the ───┘
                     diff justifies
```

1. **Triage** — the diff is bucketed (docs-only / trivial / surgical / feature), which sets a ceiling on how
   many finders run, and each lens passes an explicit SPAWN/SKIP gate. Both lists — spawned and not spawned,
   with the reason — end up in the comment.
2. **Finder wave** — the triaged lenses run in parallel as isolated read-only agents, orchestrated by the
   `Workflow` tool (with a plain Agent-tool fan-out as fallback). Each returns structured findings plus what
   it checked and dismissed.
3. **Dedup and verify** — findings are grouped by location (same file, ±3 lines). Every group holding a
   CRITICAL/HIGH, an unproven candidate or a runtime claim goes to `cr-verifier`, whose job is to **refute**
   it — by execution when the project offers a read-only way to run code.
4. **Comment** — one comment: an index table, one heading per finding, verification evidence folded into
   `<details>`, plus *Verification gaps*, *Pre-existing* and *Verified and dismissed*.
5. **Fix pass** — the main session decides finding by finding: CRITICAL/HIGH applied unless proven false
   positive (each with a test), MEDIUM/LOW applied when cheap and real, declined with a stated reason
   otherwise. Suite runs, commits pushed, summary replied on the PR.

---

## The lenses

| Agent | Covers |
|---|---|
| `cr-boundary-guard` | The project's declared critical dimension — data isolation, authorization, authentication, schema traps. Falls back to a generic access-control floor when the project declares nothing. |
| `cr-conventions` | The project's own written conventions, and APIs newer than the pinned runtime and dependencies. Base lens of every code PR. |
| `cr-exec-prober` | Runs the changed code with read-only probes; audits deleted lines for lost invariants; shell scripts and CI workflows. |
| `cr-data-layer` | Measured query cost (execution plans, not estimates), migrations, and bulk writes that bypass the model layer. |
| `cr-test-analyzer` | Coverage gaps and, above all, tests with no power to fail. |
| `cr-silent-failure-hunter` | Swallowed errors, broad catches, fallbacks that mask problems. |
| `cr-type-design` | Invariants, encapsulation and enforcement of new types. |
| `cr-comment-analyzer` | Comment accuracy against the real code; comment rot. |
| `cr-docs-guard` | Docs that assert what is no longer true; broken paths, links and commands; agent/prompt files that break their own pipeline. |
| `cr-code-reviewer` | Generalist sweep on feature-sized PRs, filtered at confidence ≥ 80. |
| `cr-verifier` | Adversarial verification of candidates — the only lens that never finds anything, only judges. |

Five of them (`cr-code-reviewer`, `cr-comment-analyzer`, `cr-silent-failure-hunter`, `cr-test-analyzer`,
`cr-type-design`) are generalized adaptations of the agents in Anthropic's
[`pr-review-toolkit`](https://github.com/anthropics/claude-code/tree/main/plugins/pr-review-toolkit) (MIT),
with the provenance recorded in each file.

---

## Requirements

- [Claude Code](https://docs.claude.com/en/docs/claude-code)
- [GitHub CLI](https://cli.github.com) (`gh`) authenticated with access to the repo
- A clean working tree on the PR branch

The `Workflow` tool is used when available; without it the pipeline falls back to a direct Agent-tool fan-out.

---

## Install

```
/plugin marketplace add MarceloCajueiro/claude-plugins
/plugin install agentic-cr@cajueiro-plugins
```

---

## Usage

From a checkout of the repo whose PR you want reviewed:

```
/cr           # reviews the PR of the current branch
/cr 123       # reviews PR #123
```

The full report is written to `/tmp/cr/<owner>-<repo>/cr_<PR>.md` — the audit artifact, with no verbosity
limit. The PR gets the readable version.

---

## Design rules

These are the rules the pipeline holds itself to, and the reason it produces fewer false positives than a
single-pass review:

1. **Review does not edit, the fix pass does not review.** No code changes between the first agent and the
   posted comment — every agent must see the same diff. A diff that shifts mid-cycle produces phantom
   findings and a comment pointing at lines that no longer exist.
2. **A finding requires a citable rule OR executable evidence** — and the rule must be one the reviewed
   project actually wrote. A fabricated citation is worse than a missed finding.
3. **A runtime claim only enters CONFIRMED by execution.** Static reading describes the path as written.
4. **Partial coverage is declared, never silent.** A cut lens, an unmeasurable cost, an undiscoverable test
   command — all of it goes under *Verification gaps* in the comment.
5. **A lens with nothing to do does not run.** An idle agent costs the same wall-clock as a working one and
   returns noise.

### Severity scheme

| Severity | Meaning |
|---|---|
| 🚨 CRITICAL | Production, security or data-integrity bug — injection, auth bypass, data leak across a boundary, data loss, destructive migration |
| ⚠️ HIGH | High incident probability — query in a loop on a hot path, race condition, unhandled error, missing tests for new logic |
| 📝 MEDIUM | Quality issue that becomes tech debt — refactor suggestions, oversized functions, context-free logging |
| 💡 LOW | Style and nits |

### Verdicts

| Verdict | Meaning |
|---|---|
| CONFIRMED | The verifier named the input and the wrong output, with proof |
| PLAUSIBLE | Real mechanism, uncertain trigger — enters with the shortest manual check attached |
| REFUTED | Constructively disproven — recorded in the comment so the next round does not reopen it |
| PRE-EXISTING | Real bug, identical on the default branch — flagged as a follow-up, not as a finding of this PR |

---

## Notes

- Comments are written in English by default; if a repo's PRs are predominantly in another language, the pipeline follows suit.
- A full run spawns several review agents — expect a few minutes and a corresponding token cost. The bucket ceiling is what keeps it bounded.
- Version 2.0.0 replaced the previous architecture (two outsourced review passes, `/cr-1`, `/cr-2`, `/cr-consolidate`) with this lens team. Those commands no longer exist; `/cr` is the whole pipeline.

---

## License

MIT © Marcelo Cajueiro — [cajueiro.tech](https://cajueiro.tech)
