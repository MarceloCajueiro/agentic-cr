# agentic-cr

Agentic code review pipeline for GitHub pull requests — **two independent review passes in parallel, one deduplicated comment on the PR, then a finding-by-finding fix pass.**

`/cr` orchestrates [Claude Code](https://docs.claude.com/en/docs/claude-code) review agents against any PR:
a baseline pass (the built-in `/code-review` skill at max effort) and a specialized pass
(`pr-review-toolkit`, aspect-picked from the diff) run concurrently in isolated agents; a third agent
merges both reports, deduplicates findings, classifies severity, and posts a single consolidated
comment on the PR. Finally, the main session walks the findings one by one — applying what's real
(with tests), declining what isn't (with a reason) — and replies on the PR.

- 🔀 **Two independent reviewers** — different skills, clean contexts, no anchoring
- 🧹 **One comment, not four** — findings deduplicated and ranked 🚨 CRITICAL → 💡 LOW
- 🔒 **Stale-proof** — every report records the PR head SHA; consolidation refuses partial or outdated inputs
- 🔧 **Fix pass with judgment** — apply or decline finding by finding, never in bulk; every fix gets a test
- 📦 **Works on any repo** — no project-specific config; `gh` infers the repository from the git remote

---

## Why two reviewers?

The pipeline doesn't invent its own review logic. It takes two well-crafted review agents that
already ship with Claude Code — the built-in `/code-review` skill and Anthropic's
`pr-review-toolkit` plugin, **each of which fans out into its own specialized sub-agents** —
and runs them in parallel, in isolated contexts, as redundant reviewers of the same PR.

The point is redundancy: there are bugs and improvements one reviewer catches and the other
doesn't. Running both and merging the results has proven very effective in practice — you get
the union of two independent reviews at the cost of reading a single consolidated comment.
Findings flagged by **both** reviewers are marked as such, which is itself a strong signal.

---

## Requirements

- [Claude Code](https://docs.claude.com/en/docs/claude-code) with the built-in `/code-review` skill
- [GitHub CLI](https://cli.github.com) (`gh`) authenticated with access to the repo
- The `pr-review-toolkit` plugin from Anthropic's marketplace:

```
/plugin marketplace add anthropics/claude-code
/plugin install pr-review-toolkit@claude-code-plugins
```

---

## Install

```
/plugin marketplace add MarceloCajueiro/claude-plugins
/plugin install agentic-cr@cajueiro-plugins
```

The commands stay short: `/cr`, `/cr-1`, `/cr-2`, `/cr-consolidate`.

---

## Usage

From a checkout of the repo whose PR you want reviewed:

```
/cr           # reviews the PR of the current branch
/cr 123       # reviews PR #123
```

Each phase is also invocable on its own:

```
/cr-1 123            # baseline review only  → /tmp/cr/<owner>-<repo>/cr_1_123.md
/cr-2 123            # specialized review only → /tmp/cr/<owner>-<repo>/cr_2_123.md
/cr-consolidate 123  # merge both files and post the consolidated comment
```

---

## How it works

```
        ┌─ cr-1: /code-review xhigh ─────────────┐
PR ──►  │            (parallel, isolated agents) ├──► cr-consolidate ──► one PR comment ──► fix pass
        └─ cr-2: /pr-review-toolkit:review-pr ───┘         (dedup + severity)                (inline)
```

1. **Parallel reviews** — two isolated agents run the baseline and specialized skills concurrently. Each writes a report with a standardized header (PR, head SHA, branch, timestamp) to `/tmp/cr/<owner>-<repo>/`.
2. **Consolidation** — a third agent verifies both reports exist and their SHAs match the current PR head (a leftover file from an old run is rejected, never merged). It deduplicates findings (same file, ±3 lines, same problem), maps everything onto one severity scheme, and posts a single comment on the PR.
3. **Fix pass** — the main session reads the consolidated comment and decides finding by finding: CRITICAL/HIGH are applied unless proven false positives (each fix with a test); MEDIUM/LOW are applied when cheap and real, declined with a stated reason otherwise. The test suite runs, fixes are committed and pushed, and a summary reply is posted on the PR.

Human review proceeds as usual afterwards — the pipeline raises the floor, it doesn't replace people.

**Phases 1 and 2 never touch your working tree.** The review agents stay on the branch you are already on and write only their report files: no checkout, no new branch, no stash or reset. That matters because the underlying skills will otherwise offer to apply fixes mid-review — which makes the second pass review a diff the first one never saw — and because `pr-review-toolkit` has been observed rolling the tree back and moving the session onto a branch of its own, silently stranding later commits off the PR. Each phase ends by checking the branch, the SHA and a clean tree against what they were at the start.

### Severity scheme

| Severity | Meaning |
|---|---|
| 🚨 CRITICAL | Production/security/data-integrity bug — injection, auth bypass, data leak, data loss, destructive migration |
| ⚠️ HIGH | High incident probability — N+1 on a hot path, race condition, unhandled error, missing tests for new logic |
| 📝 MEDIUM | Quality issue that becomes tech debt — refactor suggestions, oversized functions, context-free logging |
| 💡 LOW | Style and nits |

When in doubt, findings default to MEDIUM — severity inflation is a false positive too.

---

## Notes

- Reports live in `/tmp/cr/<owner>-<repo>/` and are keyed by PR number; the SHA check makes stale files harmless. Delete the directory to force a clean slate.
- Comments are written in English by default; if a repo's PRs are predominantly in another language, the pipeline follows suit.
- A full run spawns several review agents — expect it to take a few minutes and consume a corresponding amount of tokens.

---

## License

MIT © Marcelo Cajueiro — [cajueiro.tech](https://cajueiro.tech)
