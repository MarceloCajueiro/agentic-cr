#!/usr/bin/env python3
"""Checks the terminal summary of cr-double-check before it is printed.

Usage: lint_terminal.py <terminal.md>   exits 0 when clean, 1 with one line per problem

A terminal renders plain Markdown (headings, bold, lists) but not HTML, and it prints a
Markdown link as "text (very long url)", which breaks lines. So the summary must have:

  - no HTML at all (<details>, <summary>, <sub>, ...)
  - no Markdown link syntax [text](url)
  - a URL only at the end of a PR line (a "### " heading or a "- ✅" item), one per line
  - no rule codes (H4, R2, B2...): they live in the detail file only
  - per "Precisa de você" PR: the heading, an optional "Antes:" line, three lines per
    question (the question, "Por quê:", "Responda:") and one "Coberto:" line, nothing else
  - an ending "Detalhe completo: <absolute path>" line, optionally followed by one
    "- <repo>#<N>: <absolute path>" line per PR, every path absolute (never "~")
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HTML_RE = re.compile(r"<[A-Za-z/!][^>]*>")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+")
RULE_CODE_RE = re.compile(r"\b[HRTBDA][1-9]\b")
PR_LINE_RE = re.compile(r"^(### |- ✅ )")
MAX_QUESTIONS = 5
MAX_COVERED_ITEMS = 5


def lint(text: str) -> list[str]:
    problems = []
    lines = text.rstrip("\n").splitlines()
    for n, line in enumerate(lines, start=1):
        if HTML_RE.search(line):
            problems.append(f"line {n}: HTML does not render in a terminal: {line.strip()[:60]}")
        if MD_LINK_RE.search(line):
            problems.append(f"line {n}: a Markdown link prints as 'text (url)'; cite file:line and put the PR URL on its title line")
        urls = URL_RE.findall(line)
        if urls and (not PR_LINE_RE.match(line) or len(urls) > 1 or not line.rstrip().endswith(urls[-1])):
            problems.append(f"line {n}: a URL may only end a PR title line, once")
        if RULE_CODE_RE.search(line):
            problems.append(f"line {n}: rule code {RULE_CODE_RE.search(line).group()} belongs in the detail file, not the terminal")

    tail = len(lines)
    while tail > 0 and re.match(r"^- \S+#\d+: ", lines[tail - 1]):
        tail -= 1
    if not tail or not re.match(r"^Detalhe completo: /\S+\.md$", lines[tail - 1].strip()):
        problems.append("the output must end with 'Detalhe completo: <absolute path>.md', then the per-PR paths")
    for line in lines[tail:]:
        if not re.match(r"^- \S+#\d+: /\S+\.md$", line.strip()):
            problems.append(f"per-PR detail line needs an absolute .md path: {line.strip()[:60]}")

    # One "Precisa de você" block per "### " heading, up to the next heading.
    blocks, cur = [], None
    for line in lines:
        if line.startswith("### 🙋"):
            cur = [line]
            blocks.append(cur)
        elif line.startswith("#") or line.startswith("Detalhe completo:"):
            cur = None
        elif cur is not None and line.strip():
            cur.append(line)
    for block in blocks:
        title, body = block[0], block[1:]
        questions = sum(1 for l in body if l.strip().startswith("- Responda:"))
        antes = sum(1 for l in body if l.strip().startswith("Antes:") or l.strip().startswith("**Antes:"))
        covered = [l for l in body if l.strip().startswith("- **Coberto:**")]
        if questions == 0 and not antes:
            problems.append(f"{title[:50]}: a 'Precisa de você' PR needs a question or an 'Antes:' action")
        if questions > MAX_QUESTIONS:
            problems.append(f"{title[:50]}: {questions} questions; above {MAX_QUESTIONS}, the action is to review the whole PR")
        allowed = 1 + antes + 3 * questions + len(covered)
        if len(body) > allowed - 1 or len(covered) > 1:
            problems.append(f"{title[:50]}: {len(body) + 1} lines, expected at most {allowed} (heading, Antes, 3 per question, Coberto)")
        for l in covered:
            items = [x for x in l.split(":", 1)[1].split(",") if x.strip()]
            if len(items) > MAX_COVERED_ITEMS:
                problems.append(f"{title[:50]}: 'Coberto' lists {len(items)} items, at most {MAX_COVERED_ITEMS}")
    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    problems = lint(Path(argv[0]).read_text(encoding="utf-8"))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
