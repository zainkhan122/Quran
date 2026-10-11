"""
Publish built videos to the web folder.

Build folders are the only source of truth: each one holds

    videos.json    { "<filename>.mp4": "<reference>" }
    sources.json   the verbatim text + citation for every reference built

This tool walks those, copies the videos into web/video/, extracts a poster
frame for each, and writes web/video/manifest.json which the site renders from.
Stale videos are pruned, so the site can never show a card pointing at a file
that is no longer there.

    python tools/publish.py            # publish everything built
    python tools/publish.py --prune-posters
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "video"
BUILD_DIRS = ["output/video", "output/studio"]


def sh(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def probe(mp4: Path) -> dict:
    out = sh(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height,duration", "-show_entries", "format=duration,size",
              "-of", "json", str(mp4)])
    try:
        d = json.loads(out or "{}")
    except json.JSONDecodeError:
        return {}
    st = (d.get("streams") or [{}])[0]
    fm = d.get("format") or {}
    dur = st.get("duration") or fm.get("duration") or 0
    return {"width": st.get("width"), "height": st.get("height"),
            "seconds": round(float(dur or 0), 2),
            "size_mb": round(int(fm.get("size") or mp4.stat().st_size) / 1e6, 2)}


def poster(mp4: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1.5", "-i", str(mp4),
                    "-frames:v", "1", "-q:v", "4", str(dest)], check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune-posters", action="store_true")
    a = ap.parse_args()
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "posters").mkdir(exist_ok=True)

    items: list[dict] = []
    seen: set[str] = set()

    for bdir in BUILD_DIRS:
        d = ROOT / bdir
        idx_p, src_p = d / "videos.json", d / "sources.json"
        if not idx_p.exists():
            continue
        try:
            index = json.loads(idx_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ! {idx_p}: unreadable ({e})", file=sys.stderr)
            continue
        sources = {}
        if src_p.exists():
            for s in json.loads(src_p.read_text(encoding="utf-8")):
                sources[s.get("reference")] = s

        for filename, ref in sorted(index.items()):
            src = d / filename
            if not src.exists():
                print(f"  ! {bdir}/{filename}: listed but missing, skipped")
                continue
            if filename in seen:
                print(f"  ! {filename}: duplicate across build dirs, keeping first")
                continue
            seen.add(filename)
            meta = probe(src)
            s = sources.get(ref, {})
            build = {}
            bjson = d / filename.replace(".mp4", ".build.json")
            if bjson.exists():
                try:
                    build = json.loads(bjson.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    build = {}

            if src.stat().st_mtime != (WEB / filename).stat().st_mtime if (WEB / filename).exists() else True:
                shutil.copy2(src, WEB / filename)
            poster(src, WEB / "posters" / filename.replace(".mp4", ".jpg"))

            items.append({
                "file": filename,
                "poster": f"posters/{filename.replace('.mp4', '.jpg')}",
                "reference": ref,
                "kind": s.get("kind", build.get("kind", "")),
                "source": s.get("source", build.get("source", "")),
                "source_ar": s.get("source_ar", build.get("source_ar", "")),
                "grade": (s.get("grade", build.get("grade", ""))
                          if (s.get("kind", build.get("kind", "")) == "hadith") else ""),
                "topic": build.get("topic", "") or s.get("topic", ""),
                "topic_ur": build.get("topic_ur", ""),
                "reciter": build.get("reciter", ""),
                "arabic": s.get("arabic", build.get("arabic", "")),
                "urdu": s.get("urdu", build.get("urdu", "")),
                "english": s.get("english", build.get("english", "")),
                "collected_at": s.get("collected_at", ""),
                **meta,
            })

    # newest first by mtime, so a fresh build lands at the top of the site
    items.sort(key=lambda i: (WEB / i["file"]).stat().st_mtime, reverse=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "note": ("Every quote is fetched verbatim from api.quran.com / "
                 "api.alquran.cloud and the fawazahmed0 hadith-api and shown with "
                 "its citation. Quranic Arabic is real recitation, never "
                 "synthesised speech."),
        "items": items,
    }
    (WEB / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # prune anything the manifest no longer references
    keep = {i["file"] for i in items}
    for p in WEB.glob("*.mp4"):
        if p.name not in keep:
            p.unlink()
            print(f"  pruned {p.name}")
    if a.prune_posters:
        keep_p = {Path(i["poster"]).name for i in items}
        for p in (WEB / "posters").glob("*.jpg"):
            if p.name not in keep_p:
                p.unlink()

    print(f"[publish] {len(items)} video(s) -> {WEB}")
    for i in items:
        print(f"  {i['file']:20s} {i.get('seconds', 0):6.2f}s  "
              f"{i.get('source', '?')}  [{i.get('topic', '')}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
