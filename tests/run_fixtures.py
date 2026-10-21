#!/usr/bin/env python3
"""Runs skills/cr-double-check/scripts/signals.py over every tests/fixtures/<case>/case.json.

Each case is a synthetic PR (metadata, diff, timeline events) plus the expected outcome.
The runner writes the case as the bundle collect.sh would, runs signals.py on it, and checks:

  gates             exactly these rule IDs are gates (the mechanical "Precisa de você")
  flags_include     at least these rule IDs are flags (leads the agent must judge)
  verdict           "aprovar" requires zero gates; "precisa" with no gate is a judgment case
  bucket, ci, ...   the other expected fields, when present

It also runs a few unit checks on the pieces a fixture cannot reach: how collect.sh reads a
PR reference (no network), how a file is categorized, and how the diff parser handles a
removed line that looks like a file header.

The verdict of a judgment case is the documented answer the skill must reach by reading;
the runner cannot execute that reading, so it checks that the gates do not contradict it.
Standard library only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "cr-double-check" / "scripts"
SIGNALS = SCRIPTS / "signals.py"
COLLECT = SCRIPTS / "collect.sh"
FIXTURES = ROOT / "tests" / "fixtures"


def run_case(path: Path) -> list[str]:
    case = json.loads(path.read_text(encoding="utf-8"))
    exp = case["expected"]
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp)
        (bundle / "pr.json").write_text(json.dumps(case["pr"]), encoding="utf-8")
        (bundle / "diff.patch").write_text(case["diff"], encoding="utf-8")
        (bundle / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in case["events"]), encoding="utf-8")
        (bundle / "viewer.txt").write_text(case["viewer"] + "\n", encoding="utf-8")
        (bundle / "repo.txt").write_text(case["repo"] + "\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SIGNALS), str(bundle)], capture_output=True, text=True)
        if proc.returncode != 0:
            return [f"signals.py exited {proc.returncode}: {proc.stderr.strip()}"]
        out = json.loads((bundle / "signals.json").read_text(encoding="utf-8"))

    problems = []
    gates = sorted(out["gates"])
    if gates != sorted(exp["gates"]):
        problems.append(f"gates {gates} != expected {sorted(exp['gates'])}: {out['gates']}")
    missing = sorted(set(exp.get("flags_include", [])) - set(out["flags"]))
    if missing:
        problems.append(f"flags missing {missing} (got {sorted(out['flags'])})")
    if exp["verdict"] == "aprovar" and gates:
        problems.append(f"expected verdict aprovar but gates fired: {gates}")
    if exp["verdict"] == "precisa" and not gates and not exp.get("flags_include"):
        problems.append("a judgment-only 'precisa' case must name the flags that lead to it")
    want_pre = "precisa" if exp["gates"] else "sem-bloqueio-mecanico"
    if out["pre_verdict"] != want_pre:
        problems.append(f"pre_verdict {out['pre_verdict']} != {want_pre}")
    if "bucket" in exp and out["bucket"] != exp["bucket"]:
        problems.append(f"bucket {out['bucket']} != {exp['bucket']}")
    if "ci" in exp and out["ci"]["state"] != exp["ci"]:
        problems.append(f"ci {out['ci']['state']} != {exp['ci']}")
    if "reviews_current" in exp:
        current = bool(out["reviews"]) and out["reviews"][-1]["staleness"]["current"]
        if current != exp["reviews_current"]:
            problems.append(f"latest review current={current}, expected {exp['reviews_current']}")
    if "review_method" in exp and out["reviews"][-1]["staleness"]["method"] != exp["review_method"]:
        problems.append(f"staleness method {out['reviews'][-1]['staleness']['method']} != {exp['review_method']}")
    if "ignored" in exp and len(out["ignored_review_like_comments"]) != exp["ignored"]:
        problems.append(f"ignored review-like comments {len(out['ignored_review_like_comments'])} != {exp['ignored']}")
    if "dependency_gates" in exp and len(out["gates"].get("H7", [])) != exp["dependency_gates"]:
        problems.append(f"H7 gates {out['gates'].get('H7')} != {exp['dependency_gates']} entries")
    if "sha_source" in exp and out["reviews"][-1].get("sha_source") != exp["sha_source"]:
        problems.append(f"sha_source {out['reviews'][-1].get('sha_source')} != {exp['sha_source']}")
    if "verdicts" in exp:
        got = [row["verdict"] for rv in out["reviews"] for row in rv["index"]]
        if got != exp["verdicts"]:
            problems.append(f"index verdicts {got} != {exp['verdicts']}")
    return problems


RESOLVE_CASES = {
    "https://github.com/acme/shop/pull/123": "acme/shop 123",
    "https://github.com/acme/shop/pull/123/files": "acme/shop 123",
    "https://github.com/acme/shop/pull/123#issuecomment-456": "acme/shop 123",
    "https://github.com/acme/shop.js/pull/9?notification_referrer_id=77": "acme/shop.js 9",
    "acme/shop#45": "acme/shop 45",
    "#7": ". 7",
    "12": ". 12",
}
CATEGORY_CASES = {
    "README.md": "docs", "docs/guide.md": "docs", "docs/notes.txt": "docs", "docs/img/flow.png": "docs",
    "LICENSE": "docs", "docs/conf.py": "code", "docs/build.sh": "code", "CMakeLists.txt": "code",
    "robots.txt": "code", "requirements.txt": "code", "spec/models/cart_spec.rb": "test",
    "src/cart.test.ts": "test", "skills/x/SKILL.md": "prompt", "AGENTS.md": "prompt", "app/models/cart.rb": "code",
}
HEADER_LOOKALIKE_DIFF = (
    "diff --git a/fix.sql b/fix.sql\n--- a/fix.sql\n+++ b/fix.sql\n@@ -1,3 +1,2 @@\n"
    "--- old comment\n DELETE FROM t WHERE dup;\n-++ odd\n+UPDATE t SET a = 1;\n"
)


def run_units() -> list[str]:
    problems = []
    for ref, want in RESOLVE_CASES.items():
        got = subprocess.run(["bash", str(COLLECT), "--resolve", ref], capture_output=True, text=True).stdout.strip()
        if got != want:
            problems.append(f"collect.sh --resolve {ref!r} -> {got!r}, expected {want!r}")
    if subprocess.run(["bash", str(COLLECT), "--resolve", "not a pr"], capture_output=True).returncode == 0:
        problems.append("collect.sh --resolve accepted 'not a pr'")
    sys.path.insert(0, str(SCRIPTS))
    import signals  # noqa: E402
    for path, want in CATEGORY_CASES.items():
        if signals.categorize(path) != want:
            problems.append(f"categorize({path!r}) = {signals.categorize(path)!r}, expected {want!r}")
    parsed = signals.parse_diff(HEADER_LOOKALIKE_DIFF)
    want = {"fix.sql": {"added": [(2, "UPDATE t SET a = 1;")], "removed": [(1, "-- old comment"), (3, "++ odd")]}}
    if parsed != want:
        problems.append(f"parse_diff on a removed '-- ' line: {parsed}")
    return problems


def main() -> int:
    cases = sorted(FIXTURES.glob("*/case.json"))
    if not cases:
        print("no tests/fixtures/*/case.json found", file=sys.stderr)
        return 1
    verdicts = {"aprovar": 0, "precisa": 0}
    failed = 0
    for path in cases:
        name = path.parent.name
        problems = run_case(path)
        verdicts[json.loads(path.read_text(encoding="utf-8"))["expected"]["verdict"]] += 1
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"     {p}")
        else:
            print(f"ok   {name}")
    unit_problems = run_units()
    print("ok   unit checks" if not unit_problems else "FAIL unit checks")
    for p in unit_problems:
        print(f"     {p}")
    failed += bool(unit_problems)
    if not verdicts["aprovar"] or not verdicts["precisa"]:
        print("the fixtures must cover both verdicts", file=sys.stderr)
        return 1
    print(f"\n{len(cases) - failed}/{len(cases)} cases pass ({verdicts['aprovar']} aprovar, {verdicts['precisa']} precisa)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
