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
from islamic.relevance import check, text_for, text_from_record  # noqa: E402
from islamic.topics import list_topics  # noqa: E402

try:                                    # optional: colour only when a tty
    _TTY = sys.stdout.isatty()
except Exception:                       # pragma: no cover
    _TTY = False


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _TTY else s


def load_library(path: Path = LIBRARY, *, relevance: bool = True,
                 offline: bool | None = None) -> list[dict]:
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

    # The gate a reviewer had to apply by hand, applied by machine: a topic is
    # only allowed near a verse whose own words carry the claim the on-screen
    # headline makes. This runs HERE, in the plan, so a bad pairing stops the
    # workflow before it spends a runner on it.
    if relevance:
        refused = []
        for c in clips:
            try:
                text, how = text_for(c["ref"], c["slug"], offline=offline,
                                     topic=c["topic"])
            except Exception as e:
                # Auto mode (offline=None): a clip already published in this
                # repo can be checked against the very text it rendered, so the
                # suite stays offline and deterministic. A clip with no record
                # and no reachable publisher is a hard stop - silently skipping
                # the check is how a bad pairing ships.
                fallback = None
                if offline is None:
                    try:
                        fallback = (text_from_record(c["slug"]), "build record")
                    except Exception:
                        fallback = None
                if fallback and fallback[0]:
                    text, how = fallback
                    print(f"plan: {c['slug']} checked against its build record "
                          f"(publisher unreachable: {type(e).__name__})",
                          file=sys.stderr)
                else:
                    raise SystemExit(
                        f"cannot read the text for {c['ref']} to check its topic "
                        f"({type(e).__name__}: {e}). Use --no-relevance-check to "
                        f"plan anyway, but understand you are skipping the check "
                        f"that stops an unrelated verse being labelled with a topic.")
            rep = check(c["topic"], text)
            if not rep.ok:
                refused.append(f"  {c['slug']} [{c['ref']}] {rep.reason}")
        if refused:
            raise SystemExit(
                "REFUSED: the plan pairs a topic with a verse that does not "
                "carry it. Nothing was rendered.\n" + "\n".join(refused))
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
    ap.add_argument("--offline", action="store_true",
                    help="check topics against the published build records only")
    ap.add_argument("--no-relevance-check", action="store_true",
                    help="skip the topic<->verse gate (you almost never want this)")
    ap.add_argument("--github-output", action="store_true",
                    help="write clips=/tag=/count= for $GITHUB_OUTPUT")
    a = ap.parse_args(argv)

    clips = select(load_library(relevance=not a.no_relevance_check,
                                 offline=True if a.offline else None), a.only)
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
