#!/usr/bin/env python3
"""Checks the terminal summary of cr-double-check before it is printed.

Usage: lint_terminal.py <terminal.md>              exits 0 when clean, 1 with one line per problem
       lint_terminal.py --detail <detalhe.md> ...  checks detail files instead (see the end)

The verdict is binary and comes first: the captain must see, before anything else, whether
each PR is approved and why, in one sentence. So the summary must have:

  - a header "## cr-double-check <dd/mm> - ❌ <n> não aprova · ✅ <a> aprova", whose counts
    match the lines below it
  - right after the header, one line per judged PR, "- ❌ NÃO APROVA - <repo>#<N> - <motivo> - <url>"
    or "- ✅ APROVA - ...", before any PR block
  - one block per NÃO APROVA PR, "### <repo>#<N> - <título>", whose first line repeats its
    verdict line "❌ NÃO APROVA - <motivo>"; then an optional "Para aprovar:" action, three
    lines per question (the question, "Por quê:", "Responda:") and one "Coberto:" line,
    nothing else. An APROVA PR has no block: its summary line says it all
  - no old verdict labels ("Precisa de você", "Aprovar direto", 🙋)

A terminal renders plain Markdown (headings, bold, lists) but not HTML, and it prints a
Markdown link as "text (very long url)", which breaks lines. So it must also have:

  - no HTML at all (<details>, <summary>, <sub>, ...)
  - no Markdown link syntax [text](url)
  - a URL only at the end of a PR's summary line, once per line and once per PR
  - no rule codes (H4, R2, B2...): they live in the detail file only
  - one ending line "Detalhe completo: <absolute path>.md" (never "~"), and only one:
    the PR's own detail file when there is a single PR, the index otherwise

A detail file is opened in an editor, where Markdown links work, so it has the opposite rule
for links: every URL is a Markdown link with a short label ([sas#4299](url),
[form_sections.rb:66](url), [commit 8cf2452](url)), never a raw URL, and no HTML.
A PR's detail file ("## " title) has its verdict line right under the title; the index
("# " title) has one verdict line per PR.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HTML_RE = re.compile(r"<[A-Za-z/!][^>]*>")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+")
RULE_CODE_RE = re.compile(r"\b[HRTBDA][1-9]\b")
OLD_LABEL_RE = re.compile(r"🙋|Precisa de você|Aprovar direto")
HEADER_RE = re.compile(r"^## cr-double-check \d{2}/\d{2} - ❌ (\d+) não aprova · ✅ (\d+) aprova( · \d+ fora)?$")
SUMMARY_RE = re.compile(r"^- (❌ NÃO APROVA|✅ APROVA) - (\S+#\d+) - (.+) - (https?://\S+)$")
BLOCK_RE = re.compile(r"^### (\S+#\d+) - \S")
VERDICT_RE = re.compile(r"^(❌ NÃO APROVA|✅ APROVA) - (.+)$")
DETAIL_VERDICT_RE = re.compile(r"^(❌ NÃO APROVA|✅ APROVA) - \S")
INDEX_LINE_RE = re.compile(r"^- ((❌ NÃO APROVA|✅ APROVA) - \[\S+#\d+\]\([^)]*\) - .+|Fora: .+)$")
MAX_QUESTIONS = 5
MAX_COVERED_ITEMS = 5
MAX_REASON = 160


def one_sentence(reason: str) -> bool:
    """A reason is one sentence: short, and no full stop followed by more text."""
    return len(reason) <= MAX_REASON and not re.search(r"[.!?] ", reason)


def lint(text: str) -> list[str]:
    problems = []
    lines = text.rstrip("\n").splitlines()
    for n, line in enumerate(lines, start=1):
        if HTML_RE.search(line):
            problems.append(f"line {n}: HTML does not render in a terminal: {line.strip()[:60]}")
        if MD_LINK_RE.search(line):
            problems.append(f"line {n}: a Markdown link prints as 'text (url)'; cite file:line and put the PR URL on its summary line")
        urls = URL_RE.findall(line)
        if urls and (not SUMMARY_RE.match(line) or len(urls) > 1):
            problems.append(f"line {n}: a URL may only end a PR's summary line, once")
        if RULE_CODE_RE.search(line):
            problems.append(f"line {n}: rule code {RULE_CODE_RE.search(line).group()} belongs in the detail file, not the terminal")
        if OLD_LABEL_RE.search(line):
            problems.append(f"line {n}: old verdict label; the verdict is '❌ NÃO APROVA' or '✅ APROVA'")

    if not lines or not re.match(r"^Detalhe completo: /\S+\.md$", lines[-1].strip()):
        problems.append("the output must end with one line 'Detalhe completo: <absolute path>.md'")
    if sum(1 for l in lines if l.startswith("Detalhe completo:")) > 1 or any(re.match(r"^- \S+#\d+: /", l) for l in lines):
        problems.append("one detail path only: the PR's file for a single PR, the index for several")

    # Header, then the summary: one verdict line per PR, before the first block.
    header = HEADER_RE.match(lines[0]) if lines else None
    if not header:
        problems.append("the first line must be '## cr-double-check <dd/mm> - ❌ <n> não aprova · ✅ <a> aprova'")
    first_heading = next((i for i, l in enumerate(lines[1:], start=1) if l.startswith("#")), len(lines))
    summary = {}
    for line in lines[1:first_heading]:
        m = SUMMARY_RE.match(line)
        if m:
            verdict, ref, reason, url = m.groups()
            if ref in summary:
                problems.append(f"{ref}: listed twice in the summary")
            summary[ref] = (verdict, reason)
            if not one_sentence(reason):
                problems.append(f"{ref}: the reason must be one short sentence (at most {MAX_REASON} chars)")
        elif line.strip() and not line.startswith("Detalhe completo:"):
            problems.append(f"before the first block, only summary lines '- ❌ NÃO APROVA - ...' / '- ✅ APROVA - ...': {line.strip()[:50]}")
    if any(SUMMARY_RE.match(l) for l in lines[first_heading:]):
        problems.append("every summary line goes right after the header, before the first block")
    if not summary and not (header and header.group(3)):
        problems.append("the summary lists no PR: one line per judged PR, with its verdict and reason")
    if header:
        no, yes = int(header.group(1)), int(header.group(2))
        got_no = sum(1 for v, _ in summary.values() if v.startswith("❌"))
        if (no, yes) != (got_no, len(summary) - got_no):
            problems.append(f"header counts {no} não aprova / {yes} aprova, summary has {got_no} / {len(summary) - got_no}")
    seen_no = [ref for ref, (v, _) in summary.items() if v.startswith("❌")]
    if list(summary)[:len(seen_no)] != seen_no:
        problems.append("NÃO APROVA PRs come first in the summary, then APROVA")

    # One block per "### <repo>#<N> - " heading, up to the next heading.
    blocks, cur = [], None
    for line in lines:
        m = BLOCK_RE.match(line)
        if m:
            cur = [line]
            blocks.append((m.group(1), cur))
        elif line.startswith("#") or line.startswith("Detalhe completo:"):
            cur = None
        elif cur is not None and line.strip():
            cur.append(line)
    block_refs = [ref for ref, _ in blocks]
    if block_refs != seen_no:
        problems.append(f"one block per NÃO APROVA PR, in the summary's order: blocks {block_refs}, summary {seen_no}")
    for ref, block in blocks:
        title, body = block[0], block[1:]
        verdict = VERDICT_RE.match(body[0]) if body else None
        if not verdict:
            problems.append(f"{ref}: the first line under the heading must be the verdict '❌ NÃO APROVA - <motivo>'")
            continue
        if verdict.group(1).startswith("✅"):
            problems.append(f"{ref}: an APROVA PR has no block; its summary line says it all")
            continue
        if ref in summary and summary[ref] != verdict.groups():
            problems.append(f"{ref}: the block's verdict line must repeat its summary line's verdict and reason")
        rest = body[1:]
        questions = sum(1 for l in rest if l.strip().startswith("- Responda:"))
        action = sum(1 for l in rest if re.match(r"^\**Para aprovar:", l.strip()))
        covered = [l for l in rest if l.strip().startswith("- **Coberto:**")]
        if rest and action and not re.match(r"^\**Para aprovar:", rest[0].strip()):
            problems.append(f"{ref}: 'Para aprovar:' goes right after the verdict line")
        if questions == 0 and not action:
            problems.append(f"{ref}: a NÃO APROVA PR needs what unblocks it: a question or a 'Para aprovar:' action")
        if questions > MAX_QUESTIONS:
            problems.append(f"{ref}: {questions} questions; above {MAX_QUESTIONS}, the action is to review the whole PR")
        if covered and rest[-1] is not covered[-1]:
            problems.append(f"{ref}: 'Coberto:' is the last line of the block")
        allowed = 2 + action + 3 * questions + len(covered)
        if len(body) + 1 > allowed or len(covered) > 1:
            problems.append(f"{title[:50]}: {len(body) + 1} lines, expected at most {allowed} (heading, verdict, Para aprovar, 3 per question, Coberto)")
        for l in covered:
            items = [x for x in l.split(":", 1)[1].split(",") if x.strip()]
            if len(items) > MAX_COVERED_ITEMS:
                problems.append(f"{ref}: 'Coberto' lists {len(items)} items, at most {MAX_COVERED_ITEMS}")
    return problems


def lint_detail(text: str) -> list[str]:
    problems = []
    lines = text.splitlines()
    for n, line in enumerate(lines, start=1):
        if HTML_RE.search(line):
            problems.append(f"line {n}: no HTML in a detail file: {line.strip()[:60]}")
        bare = re.sub(r"\]\([^)]*\)", "]()", line)
        if URL_RE.search(bare):
            problems.append(f"line {n}: raw URL; make it a Markdown link with a short label: {line.strip()[:60]}")
        for label in re.findall(r"\[([^\]]*)\]\(https?://", line):
            if "://" in label or len(label) > 60:
                problems.append(f"line {n}: link label must be short ([sas#4299], [arquivo.rb:66], [commit abc1234]): {label[:40]}")
        if OLD_LABEL_RE.search(line):
            problems.append(f"line {n}: old verdict label; the verdict is '❌ NÃO APROVA' or '✅ APROVA'")

    content = [l for l in lines if l.strip()]
    if content and content[0].startswith("## "):
        if len(content) < 2 or not DETAIL_VERDICT_RE.match(content[1]):
            problems.append("the line right under the title must be the verdict '❌ NÃO APROVA - <motivo>' or '✅ APROVA - <motivo>'")
    elif content and content[0].startswith("# "):
        for line in content[1:]:
            if line.startswith("- ") and not INDEX_LINE_RE.match(line):
                problems.append(f"index line must be '- ❌ NÃO APROVA - [repo#N](url) - <motivo> - [detalhe](...)': {line[:50]}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--detail":
        problems = [f"{p}: {x}" for p in argv[1:] for x in lint_detail(Path(p).read_text(encoding="utf-8"))]
        for x in problems:
            print(x)
        return 1 if problems else 0
    problems = lint(Path(argv[0]).read_text(encoding="utf-8"))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
