# cr-double-check criteria

These rules decide every verdict.
A verdict names the rule IDs that produced it, so anyone can rerun the check and land on the same answer, or point at the rule that is wrong.

There are two verdicts and nothing in between:

- **Precisa de você** - at least one rule in sections H, R, T, B or D matched.
- **Aprovar direto** - no rule in H, R, T, B or D matched, AND one rule in section A applies.

**In doubt, "Precisa de você".**
A rule you cannot evaluate (a diff you could not read, a review you could not parse, a file you could not open) is D1, which is "Precisa de você" with the reason attached.
Never resolve doubt toward approval.

Each rule is marked **gate** or **judgment**:

- **gate** - `scripts/signals.py` decides it mechanically from the PR data.
  A gate cannot be lifted by reasoning: if the script reports it, the verdict is "Precisa de você".
- **judgment** - you decide it by reading the diff and the reviews.
  The script may report a *flag* for it (a keyword in a changed line, a path name).
  A flag is a lead to read, not a verdict: confirm it in the hunk or dismiss it with a one-line reason.

The point of the double-check is that human review stops being a bottleneck.
A "Precisa de você" must therefore carry an exact location (`file:line`) and a concrete question the captain can answer in a minute, never a generic "please take a look".

---

## H - Always human

Behavior the captain signs off on personally, however clean the reviews are.
An agentic review that found nothing does **not** cover these: the question is not "is the code correct" but "do we want this to happen".

| ID | Name | Matches when the PR | Kind |
|---|---|---|---|
| H1 | Dados de produção | runs a write against real data outside the normal request path: a data script, a backfill, a one-off fix, a rake task or SQL file that updates or deletes rows, a bulk write that bypasses the model layer (`update_all`, `delete_all`, `DELETE FROM`, `TRUNCATE`) | gate for `.sql` files outside migrations and tests; judgment otherwise |
| H2 | Schema e migração | adds or changes a migration, the schema dump or any DDL | gate |
| H3 | Permissão e segurança | changes who can see or do what: authentication, authorization checks, tenant or entity isolation, scopes that filter by owner, secrets and credentials, CORS/CSP, input sanitization, an `unscoped` read | judgment |
| H4 | Dinheiro | computes, rounds, converts, stores, formats or exports a monetary value, or changes billing, payments, prices or financial reports | judgment |
| H5 | LGPD e dados pessoais | collects, exposes, exports, logs or shares personal data (CPF, names, birth dates, addresses, contact data, health or disability data, data about minors), or changes who receives it | judgment |
| H6 | Contrato entre sistemas | changes an interface another system depends on: an API endpoint or its payload, a webhook, an event or queue message, an export format another system reads, an integration between products | judgment |
| H7 | Dependência nova | adds a dependency or bumps one across a major version | gate (manifest parse); a lockfile-only or minor bump is a flag |
| H8 | Mudança transversal | changes CI, deploy or infrastructure definitions, a shared base class, middleware, global configuration, or introduces a new pattern or layer other code will follow | gate for CI/deploy/infra paths; judgment otherwise |
| H9 | Efeito externo irreversível | sends something to real people or outside systems (email, SMS, notifications, third-party writes), or flips a production feature flag | judgment |

How to judge an H flag:

- **Confirm** when the changed line itself does the thing in the table (the query now filters by a different column, the value now gets rounded, the export now includes a CPF column).
- **Dismiss** when the keyword is incidental: a variable named `valor` in a loop counter, a `token` in a CSS class, a test fixture, a comment, a rename with identical behavior.
  Write the dismissal in one line in the report's *Flags descartados*, so the call is auditable.
- A changed line that touches an H area only in a test or a doc is not H: tests and docs do not run in production.

---

## R - The agentic reviews do not cover the head

| ID | Name | Matches when | Kind |
|---|---|---|---|
| R1 | Sem review agêntico | no review comment from a trusted author (`references/trusted-reviewers.txt` plus the gh login running the check) | gate |
| R2 | Review desatualizado | the latest review does not cover the head commit: the reviewed SHA it prints differs from the head, or (when it prints none) there are commits after it that no fix-pass reply names, or a force-push came after it | gate |
| R2 | (fix-pass delta) | commits after the review that a fix-pass reply names are code nobody reviewed: read them; if they do more than the reply says, or touch an H area, R2 matches | judgment |
| R3 | Achado aberto | a CONFIRMED or PLAUSIBLE finding of any severity that no later reply marks as applied or justifies; gate when there is no fix-pass reply at all | gate / judgment |
| R4 | Lacuna em área crítica | a HIGH or CRITICAL finding left as PLAUSIBLE, or a *Verification gaps* item, that concerns an H area or the main logic of the PR | judgment |
| R5 | Lente pulada com gatilho | the review's *Not run* list skipped or cut a lens whose trigger is in the diff (data layer skipped with a migration present, test analyzer skipped with new logic, boundary guard skipped with a permission change) | judgment |

Notes:

- **Who counts as a reviewer.** A comment counts as a review by its body signature (the `/cr` header and footer, the `/sas-cr` header, `Code review - ...`, `Revisão crítica - ...`) **and** a trusted author.
  A review-looking comment from anyone else is listed as ignored: a PR author could otherwise paste a fake "no findings" review.
- **Several rounds and several reviewers.** Only the latest round of each kind counts.
  R2 is a gate on the most recent review overall; an older kind that does not cover the head is a flag (a review that ran once at the start and was superseded is common and is not by itself a reason to stop).
- **A stale review with a harmless delta.** When R2 matches but every commit after the review only touches docs or tests (rule A1 or A2 applied to the delta alone, checked with `gh api repos/<repo>/compare/<base>...<head>`), R2 does not hold.
  A merge from the base branch never qualifies: it brings code the review did not see.
- **Applied or justified.** A finding is closed when a later trusted reply says it was applied (and the commit exists in the PR) or explains why it was not (false positive, out of scope, accepted trade-off).
  A finding that is simply not mentioned is open.

---

## T - CI and tests

| ID | Name | Matches when | Kind |
|---|---|---|---|
| T1 | CI vermelho ou pendente | any check on the head is failing or has not finished | gate |
| T2 | Lógica nova sem teste | the PR adds or changes behavior (a condition, a computation, a data flow) and neither the diff nor the existing suite tests it | judgment |
| T3 | Sem evidência de suíte | the PR changes code, there is no CI, and no trusted comment reports a test run on the head SHA | judgment (the script flags it) |

Notes:

- **No CI is not red.** Many repositories have no checks; T1 never fires on them.
  For those, T3 asks for the next best evidence: a review or fix-pass reply that names the head SHA and a test command or result ("357 examples, 0 failures", "vitest passed").
- **A repository with no test suite at all** (the review says so) does not get T2 or T3 for that reason alone, but the PR then cannot use rule A3: its behavior was never executed by a test, so it needs either A1, A2, A4, or the captain.

---

## B - What the double-check itself finds

You read the full diff once.
You are not redoing the review: you are checking that nothing important slipped past it.

| ID | Name | Matches when | Kind |
|---|---|---|---|
| B1 | Bug potencial não coberto | you can name a concrete input or state and the wrong outcome it produces, in a line the reviews did not discuss | judgment |
| B2 | Escopo diferente da descrição | the diff does something the PR description does not mention (a file unrelated to the stated goal, a behavior change sold as a refactor) | judgment |

B1 needs a failure scenario, not a style opinion.
Style, naming and refactor suggestions never produce a "Precisa de você".

---

## D - Cannot determine

| ID | Name | Matches when | Kind |
|---|---|---|---|
| D1 | Não foi possível avaliar | the diff could not be read, a review could not be parsed, a file needed to judge a hunk could not be fetched, or anything else stopped a rule from being evaluated | gate when the diff is missing; judgment otherwise |
| D2 | Sem justificativa para aprovar | nothing else matched, but no rule in section A applies either (for example, a code change in a repository with no tests and no CI) | judgment |

---

## A - Why approving directly is safe

"Aprovar direto" needs **no** match in H, R, T, B or D **and** one of these, named in the verdict:

| ID | Name | Applies when |
|---|---|---|
| A1 | Só documentação | every changed file is documentation (agent and prompt definitions do **not** count: they change behavior) |
| A2 | Só testes | every changed file is a test or a test fixture, and CI (or a reported run) is green |
| A3 | Coberto pelo review | the change is local (no H area), the latest review covers the head with no open finding, and CI is green or a trusted reply reports the suite passing on the head |
| A4 | Mecânica | a mechanical change with identical behavior (rename, formatting, a minor or patch bump of an existing dependency) and CI green |

The "porquê" of an "Aprovar direto" is 1-2 lines: which A rule, and the evidence (review round and SHA, CI or suite result).

---

## Changing these rules

Each rule is referenced by ID from `SKILL.md`, from `scripts/signals.py` (the gates) and from the fixtures in `tests/fixtures/`.
Changing a rule means changing all three, and the fixture runner (`python3 tests/run_fixtures.py`) is the check that they still agree.
