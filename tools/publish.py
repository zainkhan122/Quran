"""
Publish built videos to the web folder.

A clip is discovered by its own files, so no shared index has to be merged:

    <slug>.mp4          the render
    <slug>.build.json   everything the manifest needs (reference, citation,
                        topic, grade, the verbatim text)

`videos.json` and `sources.json` are still read when present, as a fallback for
build folders made before the build record existed. This matters for the cloud
workflow: five runners render five clips in parallel and upload only their own
two files, so there is no single cumulative index to write and nothing to
reconcile.

This tool copies the videos into web/video/, extracts a poster frame for each,
and writes web/video/manifest.json which the site renders from. Stale videos are
pruned, so the site can never show a card pointing at a file that is no longer
there.

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


def _read_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ! {p}: unreadable ({e})", file=sys.stderr)
        return default


def _file_stamp(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return -1.0


def collect(build_dirs: list[str]) -> list[dict]:
    """Every publishable clip, each described by its own build record."""
    items: list[dict] = []
    seen: set[str] = set()

    for bdir in build_dirs:
        d = ROOT / bdir
        if not d.exists():
            continue

        index = _read_json(d / "videos.json", {})
        sources = {s.get("reference"): s
                   for s in _read_json(d / "sources.json", [])}

        # Union of "listed in the index" and "an mp4 sitting here": the second
        # half is what makes a lone artifact from a CI runner publishable.
        names = {n for n in index if (d / n).exists()}
        names |= {m.name for m in d.glob("*.mp4") if m.stat().st_size > 0}

        for filename in sorted(names):
            src = d / filename
            if not src.exists():
                print(f"  ! {bdir}/{filename}: listed but missing, skipped")
                continue
            if filename in seen:
                print(f"  ! {filename}: duplicate across build dirs, keeping first")
                continue
            seen.add(filename)

            entry = index.get(filename) or {}
            ref = entry.get("reference") if isinstance(entry, dict) else entry
            build = _read_json(d / filename.replace(".mp4", ".build.json"), {})
            ref = build.get("reference") or ref or ""
            s = sources.get(ref, {})

            if not ref:
                print(f"  ! {filename}: no reference in any record, skipped")
                continue

            def pick(field: str, default=""):
                return build.get(field) or s.get(field) or default

            kind = pick("kind") or ref.split(":")[0]
            meta = probe(src)

            dest = WEB / filename
            if not dest.exists() or _file_stamp(src) != _file_stamp(dest):
                shutil.copy2(src, dest)
            poster(src, WEB / "posters" / filename.replace(".mp4", ".jpg"))

            items.append({
                "file": filename,
                "poster": f"posters/{filename.replace('.mp4', '.jpg')}",
                "reference": ref,
                "kind": kind,
                # A grade line belongs on a hadith. "Quran" under "Qur'an 30:21"
                # is noise, and it was reaching the frame once.
                "grade": pick("grade") if kind == "hadith" else "",
                "source": pick("source"),
                "source_ar": pick("source_ar"),
                "topic": pick("topic"),
                "topic_ur": pick("topic_ur"),
                "reciter": pick("reciter"),
                "timings_source": pick("timings_source"),
                "arabic": pick("arabic"),
                "urdu": pick("urdu"),
                "english": pick("english"),
                "built_at": pick("built_at") or s.get("collected_at", ""),
                **meta,
            })
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune-posters", action="store_true")
    ap.add_argument("--from", dest="dirs", action="append", default=None,
                    help="build folder to read (repeatable); default output/video, output/studio")
    ap.add_argument("--exact", action="store_true",
                    help="make the site match the build folders exactly, dropping "
                         "anything already published that this run did not build. "
                         "The default is deliberately NOT this: rendering a subset "
                         "(the cloud workflow's `only` input) must not delete the "
                         "rest of the library from the site.")
    a = ap.parse_args()
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "posters").mkdir(exist_ok=True)

    items = collect(a.dirs or BUILD_DIRS)
    freshly_built = {i["file"] for i in items}

    # Carry forward what is already live but was not rebuilt in this run.
    if not a.exact:
        previous = _read_json(WEB / "manifest.json", {})
        for old in previous.get("items", []):
            name = old.get("file", "")
            if not name or name in freshly_built:
                continue
            live = WEB / name
            if not live.exists():
                # Deleted from the site folder: that is how a clip is retired.
                continue
            kept = dict(old)
            kept.update(probe(live))
            items.append(kept)
            print(f"  kept {name} (published earlier, not rebuilt in this run)")

    # newest first by mtime, so a fresh build lands at the top of the site
    items.sort(key=lambda i: _file_stamp(WEB / i["file"]), reverse=True)

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
            print(f"  pruned {p.name} (not built and not in the previous manifest)")
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
