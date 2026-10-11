"""
Where the vertical space actually goes, per clip.

The card has four stacked zones: the topic header, the Arabic body, the two
translation halves, and the citation. Each one is laid out from the others, so
"the heading is too big" is really a question about the whole budget - and the
only honest way to answer it is to print the numbers instead of squinting at a
frame.

    python3 tools/layout_report.py                 # the published set
    python3 tools/layout_report.py --ref quran:81:8 --topic justice
    python3 tools/layout_report.py --json

Reads the same cached sources the renderer does, so it works offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic.studio import Comp, build_bases          # noqa: E402
from islamic.sources import hadith, quran             # noqa: E402
from islamic.topics import get as _topic, list_topics  # noqa: E402

#: The published set, so the default run reports on what is actually live.
PUBLISHED = [
    ("quran:81:8", "justice"),
    ("quran:30:21", "marriage"),
    ("ibnmajah:224", "knowledge"),
]


def build_comp(ref: str, topic_key: str) -> Comp:
    """Same construction `islamic.produce` uses, minus audio and ffmpeg."""
    t = _topic(topic_key)
    label_en = t.get("headline", t["label"])["en"]
    label_ur = t.get("headline", t["label"])["ur"]
    kind, _, rest = ref.partition(":")
    if kind == "quran":
        item = quran(rest, topic=label_en)[0]
        # Geometry needs the words and their metrics, not their timings - so the
        # verse is split here rather than fetching the recitation alignment.
        words = [{"text": w} for w in item.arabic.split()]
    else:
        item = hadith(kind, int(rest), topic=label_en)
        words = []
    return Comp(
        width=1080, height=1920, fps=30,
        topic_en=label_en, topic_ur=label_ur,
        reference_en=item.source, reference_ar=item.source_ar,
        grade=(item.grade or "") if item.kind == "hadith" else "",
        arabic_words=words,
        body_arabic=item.arabic if not words else "",
        urdu=item.urdu or "", english=item.english or "",
        phase1=1.0, phase2=1.0, lead=0.9, tail=1.6,
        textures=True, topic_key=topic_key,
    )


def report(comp: Comp, label: str) -> dict:
    _, _, meta, _ = build_bases(comp)
    h = comp.height
    g = meta["geometry"]
    return {
        "label": label,
        "frame_h": h,
        "headline": comp.topic_en,
        "header_top": g["header_top"],
        "header_bottom": g["header_bottom"],
        "body_top": g["body_top"],
        "body_bottom": g["body_bottom"],
        "body_h": g["body_bottom"] - g["body_top"],
        "header_pct": round((g["header_bottom"] - g["header_top"]) / h * 100, 1),
        "header_and_gap_pct": round((g["body_top"] - g["header_top"]) / h * 100, 1),
        "body_pct": round((g["body_bottom"] - g["body_top"]) / h * 100, 1),
        "heading_size": meta.get("heading_size"),
        "arabic_size": meta.get("arabic_size"),
        "urdu_size": meta.get("urdu_size"),
        "english_size": meta.get("english_size"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vertical space budget of a card")
    ap.add_argument("--ref"), ap.add_argument("--topic")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    jobs = [(a.ref, a.topic)] if a.ref else PUBLISHED
    rows = []
    for ref, key in jobs:
        if key not in list_topics():
            print(f"unknown topic {key!r}", file=sys.stderr)
            return 2
        rows.append(report(build_comp(ref, key), ref))

    if a.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"{'clip':16s} {'header':>8s} {'+gap':>7s} {'body':>8s} "
          f"{'head px':>8s} {'ar px':>6s} {'ur px':>6s} {'en px':>6s}")
    for r in rows:
        print(f"{r['label']:16s} {r['header_pct']:7.1f}% {r['header_and_gap_pct']:6.1f}% "
              f"{r['body_pct']:7.1f}% {r['heading_size']:8d} {r['arabic_size'] or 0:6d} "
              f"{r['urdu_size'] or 0:6d} {r['english_size'] or 0:6d}")
    print("\n  header = the topic plate; +gap = plate plus the space before the"
          "\n  body, which is what the reader actually perceives as the header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
