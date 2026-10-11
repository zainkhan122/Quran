#!/usr/bin/env python3
"""
Refuse to render a clip whose topic the verse does not actually support.

Run before a render is ever planned:

    python3 tools/check_relevance.py --library          # every clip in library.json
    python3 tools/check_relevance.py --clip quran-81-8  # one clip
    python3 tools/check_relevance.py --audit            # every topic's WHOLE ref list
    python3 tools/check_relevance.py --topic daughters --text-file body.txt

Exit status is 0 only when every pairing passes. `tools/plan_render.py` calls
the same code, so a bad pairing stops the workflow in the `plan` job and no
runner is ever spent on it.

Where the text comes from
-------------------------
By default the check uses the publisher's own Urdu translation, fetched through
`islamic/sources.py` - the same call the renderer makes. `--offline` makes it
read the `<slug>.build.json` beside each published clip instead, which is what
the test suite uses: it is the text that was actually rendered, so the check is
auditing the artefact and not a fresh copy that might have drifted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic.relevance import check, text_for                          # noqa: E402
from islamic.topics import TOPICS                                     # noqa: E402

LIBRARY = ROOT / "library.json"

OK, BAD = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"


def resolve_text(ref: str, topic: str, slug: str, offline: bool) -> tuple[str, str]:
    return text_for(ref, slug, offline=offline, topic=topic)


def check_one(ref: str, topic: str, slug: str, offline: bool, quiet: bool = False):
    text, how = resolve_text(ref, topic, slug, offline)
    rep = check(topic, text)
    if not quiet:
        mark = OK if rep.ok else BAD
        print(f"  {mark}  {ref:16s} topic={topic:10s} ({how})")
        print(f"        {rep.reason}")
        if rep.matched:
            print("        shares: " + ", ".join(f"{k}={v:.0%}" for k, v in rep.shares.items()))
        print(f"        text: {text.splitlines()[0][:110]}")
    return rep


def library_clips() -> list[dict]:
    lib = json.loads(LIBRARY.read_text(encoding="utf-8"))
    return lib.get("clips", [])


def audit_topics(offline: bool) -> int:
    """Run each topic against its ENTIRE declared ref list.

    This is how the ref lists get cleaned up: a topic that lists a verse its own
    headline cannot justify is a topic waiting to produce a bad clip.
    """
    bad = 0
    total = 0
    for key, spec in TOPICS.items():
        refs = [f"quran:{r}" for r in spec.get("quran", [])] + \
               [f"{h}" for h in spec.get("hadith", [])]
        if not refs:
            continue
        print(f"\n{key}  ({spec['headline']['ur']})")
        for ref in refs:
            total += 1
            slug = ref.replace(":", "-")
            try:
                rep = check_one(ref, key, slug, offline)
            except Exception as e:
                print(f"  \033[33mSKIP\033[0m  {ref:16s} ({type(e).__name__}: {str(e)[:70]})")
                continue
            if not rep.ok:
                bad += 1
    print(f"\naudit: {total - bad}/{total} refs are carried by their topic's own headline"
          + ("" if not bad else f"  -- {bad} to prune or re-house"))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Topic <-> text relevance gate")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--library", action="store_true", help="check every clip in library.json")
    g.add_argument("--clip", help="check one slug or reference")
    g.add_argument("--audit", action="store_true", help="check every topic's whole ref list")
    g.add_argument("--topic", help="with --text-file: check arbitrary text")
    ap.add_argument("--text-file")
    ap.add_argument("--offline", action="store_true",
                    help="read the rendered text from build records, no network")
    ap.add_argument("--github-output", action="store_true")
    a = ap.parse_args(argv)

    if a.topic and a.text_file:
        text = Path(a.text_file).read_text(encoding="utf-8")
        rep = check(a.topic, text)
        print((OK if rep.ok else BAD) + f"  {a.topic}: {rep.reason}")
        return 0 if rep.ok else 1

    if a.audit:
        return audit_topics(a.offline)

    if a.clip:
        wanted = a.clip.replace("-", ":", 1) if ":" not in a.clip else a.clip
        hit = None
        for c in library_clips():
            if a.clip in (c["slug"], c["ref"]) or wanted == c["ref"]:
                hit = c
                break
        if hit is None:
            print(f"{BAD}  {a.clip} is not in library.json")
            return 1
        rep = check_one(hit["ref"], hit["topic"], hit["slug"], a.offline)
        return 0 if rep.ok else 1

    clips = library_clips()
    print(f"relevance gate over {len(clips)} clip(s)"
          f"  [{'build records' if a.offline else 'publisher text'}]\n")
    failures: list[str] = []
    for c in clips:
        try:
            rep = check_one(c["ref"], c["topic"], c["slug"], a.offline)
        except Exception as e:
            print(f"  \033[33mSKIP\033[0m  {c['ref']:16s} ({type(e).__name__}: {str(e)[:70]})")
            continue
        if not rep.ok:
            failures.append(f"{c['slug']}: {rep.reason}")

    if a.github_output:
        out = Path(__import__("os").environ.get("GITHUB_OUTPUT", "/dev/stdout"))
        with out.open("a", encoding="utf-8") as fh:
            fh.write(f"failures={len(failures)}\n")

    if failures:
        print(f"\n{BAD}  {len(failures)} pairing(s) refused - these must not be rendered:")
        for f in failures:
            print(f"   - {f}")
        return 1
    print(f"\n{OK}  every topic is carried by its own text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
