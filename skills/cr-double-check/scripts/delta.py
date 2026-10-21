#!/usr/bin/env python3
"""What changed after the latest review, fetched for the R2 judgment of cr-double-check.

Usage: delta.py <bundle-dir>

Reads signals.json (and pr.json) from a bundle, and for every commit after the latest
review (the unreviewed ones and the fix-pass ones) fetches its parents and files with
`gh api repos/<repo>/commits/<sha>`. Writes delta.json next to them and prints it.

For a merge commit, GitHub lists the files against the first parent, which is what the
merge brought from the base branch. `touches_reviewed_files` is the part of that list the
reviewed diff had changed (base branch...reviewed SHA): the only place a merge can alter
code the review saw. Read-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signals import categorize  # noqa: E402


def gh_json(*args: str):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    bundle = Path(argv[0])
    signals = json.loads((bundle / "signals.json").read_text())
    pr = json.loads((bundle / "pr.json").read_text())
    repo = signals["pr"]["repo"]
    pr_files = {f["path"] for f in pr.get("files") or []}
    if not signals["reviews"]:
        print("no review: nothing to compare against", file=sys.stderr)
        return 1
    latest = signals["reviews"][-1]
    st = latest["staleness"]
    commits = [dict(c, role="unreviewed") for c in st["unreviewed"]] + [dict(c, role="fix-pass") for c in st["fix_pass"]]

    reviewed = latest.get("reviewed_sha") or st.get("base")
    reviewed_files: set[str] = set()
    if reviewed:
        cmp = gh_json("api", f"repos/{repo}/compare/{pr['baseRefName']}...{reviewed}")
        reviewed_files = {f["filename"] for f in cmp.get("files") or []}

    out_commits = []
    totals = {"additions": 0, "deletions": 0, "files": set(), "categories": set()}
    for c in commits:
        full = next(x["oid"] for x in pr["commits"] if x["oid"].startswith(c["oid"]))
        data = gh_json("api", f"repos/{repo}/commits/{full}")
        parents = [p["sha"] for p in data.get("parents") or []]
        files = [{"path": f["filename"], "status": f.get("status"), "additions": f.get("additions", 0),
                  "deletions": f.get("deletions", 0), "category": categorize(f["filename"])}
                 for f in data.get("files") or []]
        merge = len(parents) > 1
        entry = {"oid": full[:12], "role": c["role"], "msg": c["msg"], "merge": merge, "parents": [p[:12] for p in parents]}
        if merge:
            # What the base branch brought; only its overlap with the reviewed files can change reviewed code.
            entry["base_files"] = len(files)
            entry["touches_reviewed_files"] = sorted(f["path"] for f in files if f["path"] in reviewed_files)
            entry["touches_pr_files"] = sorted(f["path"] for f in files if f["path"] in pr_files)
        else:
            entry["files"] = files
            for f in files:
                totals["additions"] += f["additions"]
                totals["deletions"] += f["deletions"]
                totals["files"].add(f["path"])
                totals["categories"].add(f["category"])
        out_commits.append(entry)

    out = {
        "review": {"kind": latest["kind"], "at": latest["at"], "reviewed_sha": reviewed, "sha_source": latest.get("sha_source")},
        "head": pr["headRefOid"],
        "reviewed_files": sorted(reviewed_files),
        "pr_size": {"additions": pr.get("additions"), "deletions": pr.get("deletions"), "files": len(pr_files)},
        "delta_size": {"additions": totals["additions"], "deletions": totals["deletions"],
                       "files": sorted(totals["files"]), "categories": sorted(totals["categories"])},
        "commits": out_commits,
        "force_pushed_after": st["force_pushed_after"],
        "compare_hint": f"gh api repos/{repo}/compare/{reviewed}...{pr['headRefOid']}" if reviewed else "",
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    (bundle / "delta.json").write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
