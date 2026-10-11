#!/usr/bin/env python3
"""
Keep the repo and the workspace inside their budgets.

Two different budgets, two different problems:

* **The workspace** has a hard 128 MB snapshot limit. Going over it does not
  warn, it *drops files* — and on 2026-10-11 it dropped 22 of them, including
  the git objects for a finished commit. Nothing here can stop that; what helps
  is knowing the number before the session ends.
* **The repo** accumulates render artefacts. `web/video/` must keep whatever the
  site links to, but the GitHub *Releases* hold a second copy of every render,
  and those are prunable.

What is safe to delete and what is not is the whole design of this file:

    web/video/*.mp4          KEPT     the published set; the site links to it
    web/video/*.build.json   KEPT     the gate reads provenance from these
    Release assets           PRUNABLE they duplicate web/video for a given clip
    output/ .content-cache/  SCRATCH  git-ignored; delete any time
    assets/motifs/*.png      KEPT     background art, one per topic

    python3 tools/cleanup.py                 # report only, changes nothing
    python3 tools/cleanup.py --scratch       # delete git-ignored scratch
    python3 tools/cleanup.py --prune-releases --keep 4
    python3 tools/cleanup.py --json

`--prune-releases` needs a token in `$GITHUB_TOKEN` or `/tmp/.ght` and refuses
to touch a release whose tag is referenced anywhere in the repo's docs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
REPO = "zainkhan122/Quran"

API = "https://api.github.com"
SCRATCH = [ROOT / "output", ROOT / ".content-cache", ROOT / "__pycache__"]

#: Bigger than this and a tracked file is worth a look.
BIG_TRACKED_MB = 3.0
#: Workspace warning threshold, in MB against the 128 MB snapshot limit.
WS_WARN_MB = 118


def sh(cmd: list[str], stdin_text: str | None = None, **kw) -> str:
    p = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True, **kw)
    return p.stdout


def dir_mb(p: Path) -> float:
    if not p.exists():
        return 0.0
    if p.is_file():
        return p.stat().st_size / 1e6
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total / 1e6


def workspace_mb() -> float:
    """Workspace size as the snapshot counts it.

    `.cache` is excluded by the snapshot, so it must be excluded here too -
    otherwise the number is 60 MB high and a real overrun hides underneath a
    known-false alarm.
    """
    skip = {".cache", "__pycache__", "node_modules", ".venv", "dist", "build"}
    total = 0
    for f in WORKSPACE.rglob("*"):
        if any(part in skip for part in f.parts):
            continue
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total / 1e6


def token() -> str | None:
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    p = Path("/tmp/.ght")
    if p.exists():
        return p.read_text().strip()
    return None


def api(path: str, tok: str | None, method: str = "GET"):
    req = urllib.request.Request(f"{API}{path}", method=method)
    req.add_header("Accept", "application/vnd.github+json")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


# ---------------------------------------------------------------------------
def superseded_blobs() -> list[tuple[float, str, str]]:
    """Clip blobs still in history that no current file needs any more.

    Every re-render commits a new mp4 over the old one, and the old blob stays
    in `.git` for ever: after three re-renders the repository carried 26.6 MB of
    clip bytes for a 10.7 MB published set. They are invisible to `du` on the
    working tree, which is exactly why they need reporting.
    """
    out = sh(["git", "rev-list", "--objects", "--all"], cwd=ROOT)
    rows = sh(["git", "cat-file", "--batch-check=%(objecttype) %(objectname) "
               "%(objectsize) %(rest)"], cwd=ROOT, stdin_text=out)
    current = {}
    for rel in sh(["git", "ls-files"], cwd=ROOT).splitlines():
        try:
            current[rel] = (ROOT / rel).stat().st_size
        except OSError:
            current[rel] = 0
    stale = []
    for line in rows.splitlines():
        parts = line.split(" ", 3)
        if len(parts) < 4 or parts[0] != "blob":
            continue
        size, rel = int(parts[2]), parts[3]
        if rel.startswith("web/video/") and rel.endswith(".mp4") \
                and size != current.get(rel):
            stale.append((round(size / 1e6, 1), parts[1][:10], rel))
    stale.sort(reverse=True)
    return stale


def report() -> dict:
    ws = workspace_mb()
    git_dir = dir_mb(ROOT / ".git")
    repo = dir_mb(ROOT) - git_dir
    tracked = sh(["git", "ls-files", "-z"], cwd=ROOT).split("\0")
    big = []
    for rel in tracked:
        if not rel:
            continue
        p = ROOT / rel
        try:
            mb = p.stat().st_size / 1e6
        except OSError:
            continue
        if mb >= BIG_TRACKED_MB:
            big.append((round(mb, 1), rel))
    big.sort(reverse=True)

    scratch = {str(p.relative_to(ROOT)): round(dir_mb(p), 1) for p in SCRATCH if p.exists()}
    loose = [{"name": p.name, "mb": round(p.stat().st_size / 1e6, 1)}
             for p in sorted(WORKSPACE.glob("*"))
             if p.is_file() and p.name != "naat-ai-ahead.bundle"]

    stale = superseded_blobs()
    return {"workspace_mb": round(ws, 1), "snapshot_limit_mb": 128.0,
            "repo_mb": round(repo, 1), "git_mb": round(git_dir, 1),
            "scratch": scratch, "big_tracked": big, "loose_workspace_files": loose,
            "superseded_clip_mb": round(sum(s[0] for s in stale), 1),
            "superseded_clips": stale[:8]}


def print_report(r: dict) -> None:
    head = r["workspace_mb"] > WS_WARN_MB
    mark = "\033[31m!\033[0m" if head else "\033[32mok\033[0m"
    print(f"\n\033[1m== budget\033[0m")
    print(f"   {mark} workspace  {r['workspace_mb']:6.1f} MB / {r['snapshot_limit_mb']:.0f} MB"
          f"   (headroom {r['snapshot_limit_mb'] - r['workspace_mb']:.1f} MB)")
    print(f"      repo       {r['repo_mb']:6.1f} MB   (.git {r['git_mb']:.1f} MB)")

    if r["scratch"]:
        print("\n\033[1m== scratch (git-ignored, safe to delete)\033[0m")
        for k, v in sorted(r["scratch"].items(), key=lambda x: -x[1]):
            print(f"      {v:6.1f} MB  {k}")
        print("      delete with: python3 tools/cleanup.py --scratch")

    if r["big_tracked"]:
        print("\n\033[1m== largest tracked files\033[0m")
        for mb, rel in r["big_tracked"][:10]:
            print(f"      {mb:6.1f} MB  {rel}")

    if r.get("superseded_clip_mb"):
        print("\n\033[1m== superseded clips still in history\033[0m")
        for mb, sha, rel in r["superseded_clips"]:
            print(f"      {mb:6.1f} MB  {sha}  {rel}")
        print(f"      {r['superseded_clip_mb']:.1f} MB of retired renders are still"
              f" in .git.\n"
              f"      `git gc` will NOT reclaim them: they are reachable from the"
              f" commits that published\n"
              f"      them, so only a history rewrite frees the space - the same"
              f" procedure used for the\n"
              f"      abandoned output/ audio on 2026-10-11 (docs/CLEANUP-LOG.md):\n"
              f"        git filter-branch -f --index-filter \\\n"
              f"          'git rm -r --cached --ignore-unmatch <path>' -- main\n"
              f"        git reflog expire --expire=now --all && git gc --prune=now\n"
              f"        git push --force-with-lease origin main   # then re-verify\n"
              f"      Batch it: every re-render adds another ~11 MB, so squeeze when"
              f" the workspace\n"
              f"      is within ~15 MB of the limit rather than after every render.")

    if r["loose_workspace_files"]:
        print("\n\033[1m== loose files in the workspace\033[0m")
        for f in r["loose_workspace_files"]:
            print(f"      {f['mb']:6.1f} MB  {f['name']}")
        print("      every one of these should be in the repo or deleted")

    if not head:
        print(f"\n\033[32m   workspace is inside budget.\033[0m")
    else:
        print(f"\n\033[31m   OVER BUDGET. The next snapshot will drop files. Run"
              f" --scratch, then move anything else into the repo.\033[0m")


# ---------------------------------------------------------------------------
def clean_scratch() -> None:
    print("\n\033[1m== removing scratch\033[0m")
    for p in SCRATCH:
        if p.exists():
            mb = dir_mb(p)
            shutil.rmtree(p, ignore_errors=True)
            print(f"      removed {mb:6.1f} MB  {p.relative_to(ROOT)}")
    print("      (all of it is git-ignored and regenerated on demand)")


def cleanup_releases(keep: int, dry: bool) -> int:
    """Delete Release assets for all but the newest `keep` releases.

    Refuses to delete a release whose tag appears anywhere in the repo's
    markdown, so a tag a document points at cannot be pruned out from under it.
    """
    tok = token()
    if not tok:
        print("\n\033[31m   --prune-releases needs a token (GITHUB_TOKEN or /tmp/.ght)."
              " Nothing done.\033[0m")
        return 1

    print(f"\n\033[1m== releases (keeping the newest {keep})\033[0m")
    try:
        rels = api(f"/repos/{REPO}/releases?per_page=100", tok) or []
    except urllib.error.HTTPError as e:
        print(f"      API error: {e}")
        return 1
    if not rels:
        print("      none")
        return 0

    docs = " ".join(p.read_text(encoding="utf-8", errors="ignore")
                    for p in ROOT.glob("*.md"))
    rels.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    freed = 0.0
    for i, r in enumerate(rels):
        tag = r.get("tag_name", "")
        assets = r.get("assets") or []
        size = sum(a.get("size", 0) for a in assets) / 1e6
        if i < keep:
            print(f"      keep   {tag:26s} {len(assets)} asset(s) {size:7.1f} MB")
            continue
        if re.search(re.escape(tag), docs):
            print(f"      KEEP   {tag:26s} referenced by a document - not touching it")
            continue
        if dry:
            print(f"      would  {tag:26s} {len(assets)} asset(s) {size:7.1f} MB")
            continue
        for a in assets:
            try:
                api(f"/repos/{REPO}/releases/assets/{a['id']}", tok, method="DELETE")
                freed += a.get("size", 0) / 1e6
            except urllib.error.HTTPError as e:
                print(f"        asset {a.get('name')}: {e}")
        try:
            api(f"/repos/{REPO}/releases/{r['id']}", tok, method="DELETE")
            print(f"      pruned {tag:26s} freed {size:7.1f} MB")
        except urllib.error.HTTPError as e:
            print(f"      prune {tag}: {e}")

    print(f"      total freed: {freed:.1f} MB" if not dry else "      (dry run)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Repo + workspace budget housekeeping")
    ap.add_argument("--scratch", action="store_true", help="delete git-ignored scratch")
    ap.add_argument("--prune-releases", action="store_true",
                    help="delete older Release assets (needs a token)")
    ap.add_argument("--keep", type=int, default=4, help="releases to keep (default 4)")
    ap.add_argument("--dry-run", action="store_true", help="report only, never delete")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    dry = a.dry_run
    r = report()
    if a.json and not (a.scratch or a.prune_releases):
        print(json.dumps(r, indent=2))
        return 0
    print_report(r)

    rc = 0
    if a.scratch:
        if dry:
            print("\n   (dry run: scratch not removed)")
        else:
            clean_scratch()
    if a.prune_releases:
        rc = cleanup_releases(a.keep, dry)

    if not (a.scratch or a.prune_releases):
        print("\n   nothing was changed. Pass --scratch and/or --prune-releases.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
