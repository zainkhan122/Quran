#!/usr/bin/env python3
"""
Turn library.json into a render matrix for the cloud workflow.

Kept out of the YAML on purpose: inline python in a workflow cannot be run or
tested locally, and this is the one part of the workflow that decides what gets
built. Here it can be tried before it ever reaches a runner.

    python3 tools/plan_render.py                    # every clip in the library
    python3 tools/plan_render.py --only quran-81-8
    python3 tools/plan_render.py --only quran:30:21,ibnmajah-224
    python3 tools/plan_render.py --tag renders-2026-11-01
    python3 tools/plan_render.py --plan             # human-readable summary

With --github-output it writes `clips=`, `tag=` and `count=` for
$GITHUB_OUTPUT. Without it, it prints the JSON plan.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "library.json"

# topics.py owns the topic list; importing it keeps the plan honest about which
# topics the renderer can actually select a headline and a motif for.
sys.path.insert(0, str(ROOT))
from islamic.topics import list_topics  # noqa: E402


def load_library(path: Path = LIBRARY) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"no clip plan at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    clips = data.get("clips") or []
    if not clips:
        raise SystemExit(f"{path} lists no clips")

    topics = set(list_topics())
    seen: set[str] = set()
    for c in clips:
        for field in ("slug", "ref", "topic"):
            if not c.get(field):
                raise SystemExit(f"clip missing '{field}': {c}")
        slug, ref, topic = c["slug"], c["ref"], c["topic"]
        expected = ref.replace(":", "-")
        if slug != expected:
            raise SystemExit(
                f"slug/ref mismatch: slug '{slug}' but ref '{ref}' implies "
                f"'{expected}'. The site resolves videos by slug, so this cannot "
                f"be left to chance.")
        if topic not in topics:
            raise SystemExit(f"unknown topic '{topic}' in clip '{slug}' "
                             f"(have: {', '.join(sorted(topics))})")
        if slug in seen:
            raise SystemExit(f"duplicate slug '{slug}'")
        # A Qur'an clip must carry its recitation; a hadith card may legitimately
        # be silent (no recitation exists, and an isnad is never auto-narrated).
        # The gate is told which one it is looking at rather than guessing.
        c["require_audio"] = ref.startswith("quran:")
        seen.add(slug)
    return clips


def select(clips: list[dict], only: str) -> list[dict]:
    """`only` accepts slugs or references, space or comma separated."""
    want = [w for w in only.replace(",", " ").split() if w]
    if not want:
        return clips
    by_slug = {c["slug"]: c for c in clips}
    by_ref = {c["ref"]: c for c in clips}
    out, missing = [], []
    for w in want:
        hit = by_slug.get(w) or by_ref.get(w)
        if hit is None:
            missing.append(w)
        elif hit not in out:
            out.append(hit)
    if missing:
        raise SystemExit(
            f"not in the library: {', '.join(missing)}\n"
            f"known: {', '.join(c['slug'] for c in clips)}")
    return out


def default_tag(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return "renders-" + now.strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan a cloud render.")
    ap.add_argument("--only", default="", help="slugs or refs; empty = all")
    ap.add_argument("--tag", default="", help="release tag (default renders-YYYY-MM-DD)")
    ap.add_argument("--plan", action="store_true", help="print a summary, not JSON")
    ap.add_argument("--github-output", action="store_true",
                    help="write clips=/tag=/count= for $GITHUB_OUTPUT")
    a = ap.parse_args(argv)

    clips = select(load_library(), a.only)
    tag = a.tag.strip() or default_tag()

    if a.plan:
        print(f"tag:   {tag}")
        print(f"count: {len(clips)}")
        for c in clips:
            print(f"  {c['slug']:<18} {c['ref']:<16} {c['topic']}")
        return 0

    if a.github_output:
        # JSON on one line: the matrix needs a list of objects, and a newline in
        # the value would break $GITHUB_OUTPUT.
        print("clips=" + json.dumps(clips, separators=(",", ":"), ensure_ascii=False))
        print("tag=" + tag)
        print("count=" + str(len(clips)))
        return 0

    print(json.dumps({"tag": tag, "count": len(clips), "clips": clips},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
