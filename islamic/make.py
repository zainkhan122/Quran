"""
Islamic Video Studio - CLI.

    python -m islamic.make --topic marriage --refs quran:30:21,bukhari:1 --out output/video
    python -m islamic.make --refs quran:65:2-3
    python -m islamic.make --topic daughters --list

Text is always fetched verbatim with a citation. Nothing is written by a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .topics import TOPICS, get, list_topics
from .video import VideoSpec, build_video
from .sources import ContentError, clean_isnad, load_items, save


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Turn citable Islamic text into a video.")
    ap.add_argument("--topic", help=f"one of: {', '.join(list_topics())}")
    ap.add_argument("--refs", help="comma-separated refs, e.g. quran:30:21,bukhari:1")
    ap.add_argument("--list", action="store_true", help="list topics and exit")
    ap.add_argument("--out", default="output/video")
    ap.add_argument("--engine", default="mms", choices=["mms", "mms-ft", "gtts"],
                    help="Urdu narration voice")
    ap.add_argument("--english", action="store_true", help="add an English card phase")
    ap.add_argument("--no-backing", action="store_true")
    ap.add_argument("--max-items", type=int, default=1,
                    help="how many items from the topic to render")
    ap.add_argument("--landscape", action="store_true", help="16:9 instead of 9:16")
    a = ap.parse_args(argv)

    if a.list or not (a.topic or a.refs):
        print(json.dumps({k: {"label": v["label"]["en"], "quran": v.get("quran", []),
                              "note": v.get("note", "")} for k, v in TOPICS.items()},
                         ensure_ascii=False, indent=2))
        return 0

    topic_title = ""
    if a.refs:
        refs = [r.strip() for r in a.refs.split(",") if r.strip()]
        topic = a.topic or ""
        topic_title = get(a.topic)["label"]["en"] if a.topic else ""
    else:
        t = get(a.topic)
        refs = [f"quran:{r}" for r in t.get("quran", [])] + t.get("hadith", [])
        topic = t["label"]["en"]
        topic_title = topic

    print(f"[studio] fetching {len(refs)} verbatim reference(s)...")
    items = load_items(refs, topic=topic)

    # Merge into a cumulative citation file. Overwriting it meant the web
    # manifest lost the citations of every video except the most recent run.
    cit_path = Path(a.out) / "sources.json"
    known: list = []
    if cit_path.exists():
        try:
            known = json.loads(cit_path.read_text(encoding="utf-8"))
        except Exception:
            known = []
    by_ref = {c.get("reference"): c for c in known}
    for it in items:
        d = asdict(it)
        d["topic"] = topic_title or d.get("topic")
        by_ref[it.reference] = d
    cit_path.parent.mkdir(parents=True, exist_ok=True)
    cit_path.write_text(json.dumps(list(by_ref.values()), ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[studio] {len(items)} item(s) fetched; {len(by_ref)} citations on file")

    spec = VideoSpec(width=1920, height=1080) if a.landscape else VideoSpec()
    results = []
    for i, item in enumerate(items[: a.max_items]):
        print(f"\n--- {item.reference} : {item.source}")
        print(f"    grade: {item.grade or 'n/a'}")
        stem = item.reference.replace(":", "-")
        # narration reads the Urdu where available, else falls back to no narration
        if not item.urdu and item.kind == "hadith":
            print("    (no Urdu edition for this collection — card only, no narration)")
        try:
            info = build_video(
                item,
                Path(a.out) / f"{stem}.mp4",
                work_dir=Path(a.out) / f"work_{stem}",
                spec=spec, engine=a.engine,
                include_english=a.english, add_backing=not a.no_backing,
            )
            results.append(info)
            # record the filename -> reference mapping: filenames have ':' replaced
            # by '-', which is not reversible (quran-30-21 -> quran:30-21, wrong)
            idx_path = Path(a.out) / "videos.json"
            idx = {}
            if idx_path.exists():
                try:
                    idx = json.loads(idx_path.read_text(encoding="utf-8"))
                except Exception:
                    idx = {}
            idx[Path(info["file"]).name] = item.reference
            idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            print(f"    -> {info['file']}  {info['duration']}s  {info['size_mb']} MB")
            for s in info["segments"]:
                print(f"       {s['kind']:8s} {s['seconds']:>6.2f}s  audio={s['audio']}")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {e}")
            results.append({"reference": item.reference, "error": str(e)})

    (Path(a.out) / "build.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[studio] done -> {a.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ContentError as e:
        print(f"content error: {e}", file=sys.stderr)
        sys.exit(2)
