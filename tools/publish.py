"""
Publish built videos to the web folder.

A clip is discovered by its own files, so no shared index has to be merged:

    <slug>.mp4          the render
    <slug>.build.json   everything the manifest needs (reference, citation,
                        topic, grade, the verbatim text)

The build record is published alongside the clip, not only kept in the build
folder. Two reasons, and the second one was found by a test:

  * a published video should carry its citation wherever it goes, and the record
    IS the citation — reference, source, grade, and the verbatim text;
  * the build folder is git-ignored, so on a fresh checkout (a cloud runner, a
    new laptop) the committed clips had no record to check them against and the
    gate failed them all as unverifiable. Provenance has to be in the repository
    for the repository's own checks to work.

`videos.json` and `sources.json` are still read when present, as a fallback for
build folders made before the build record existed. This matters for the cloud
workflow: five runners render five clips in parallel and upload only their own
two files, so there is no single cumulative index to write and nothing to
reconcile.

Every clip must pass tools/check_video.py before it is copied; a clip that fails
is held back with its reason printed, and the run exits non-zero so CI notices.
The gate is repeated here even though the render job already runs it, because
this is the last point before publication and it is cheap.

MEDIA IS NOT COMMITTED (2026-10-11). The mp4s and posters this writes into
web/video/ are git-ignored. Each item records the GitHub Release that holds its
media (`--release TAG`), the render workflow uploads the files there, and the
Pages workflow pulls them back into the site at deploy time
(tools/fetch_media.py). Git keeps only what is small and must be reviewable:
the manifest and each clip's build record - the citation. Before this, every
re-render added ~11 MB of permanent history and the repo needed a history
rewrite three times in one day.

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


def gate(mp4: Path) -> tuple[bool, str]:
    """Run the publication gate. Returns (passed, first_reason)."""
    cmd = [sys.executable, str(ROOT / "tools" / "check_video.py"), str(mp4)]
    # A Qur'an clip must carry its recitation. A hadith card may be silent, so the
    # flag is derived from the build record rather than assumed either way.
    bj = mp4.with_suffix(".build.json")
    try:
        build = json.loads(bj.read_text(encoding="utf-8")) if bj.exists() else {}
    except json.JSONDecodeError:
        build = {}
    if build.get("kind") == "quran":
        cmd.append("--require-audio")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode == 0:
        return True, ""
    for line in (p.stderr or "").splitlines():
        if line.startswith("FAIL"):
            return False, line.replace("FAIL", "").strip()
    return False, (p.stderr or p.stdout or "gate failed").strip()[:160]


def _file_stamp(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return -1.0


def library_refs() -> set[str]:
    """What is still planned. A published clip whose reference has left
    library.json is retired - that is now the one way to take a clip down."""
    d = _read_json(ROOT / "library.json", {})
    return {c.get("ref", "") for c in d.get("clips", [])}


def collect(build_dirs: list[str], release: str = "") -> tuple[list[dict], list[str]]:
    """Every publishable clip, each described by its own build record.

    Returns (items, held_back_reasons). A clip that fails the gate is not an
    error to swallow: it is reported and the caller fails the run.
    """
    items: list[dict] = []
    held: list[str] = []
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

            ok, why = gate(src)
            if not ok:
                print(f"  ! {filename}: HELD BACK — {why}")
                held.append(f"{filename}: {why}")
                continue

            def pick(field: str, default=""):
                return build.get(field) or s.get(field) or default

            kind = pick("kind") or ref.split(":")[0]
            meta = probe(src)

            dest = WEB / filename
            if not dest.exists() or _file_stamp(src) != _file_stamp(dest):
                shutil.copy2(src, dest)
            # Publish the citation next to the clip (see the module docstring).
            if build:
                rec = WEB / filename.replace(".mp4", ".build.json")
                rec.write_text(json.dumps(build, ensure_ascii=False, indent=2),
                               encoding="utf-8")
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
                "narration": build.get("narration") or {},
                # where the media lives; "" for a local-only preview build
                "release": release,
                **meta,
            })
            if build and release:
                build["release"] = release
                rec = WEB / filename.replace(".mp4", ".build.json")
                rec.write_text(json.dumps(build, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    return items, held


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
    ap.add_argument("--release", default="",
                    help="GitHub Release tag that will hold this run's media; "
                         "recorded per item so Pages can fetch it back")
    a = ap.parse_args()
    WEB.mkdir(parents=True, exist_ok=True)
    (WEB / "posters").mkdir(exist_ok=True)

    items, held = collect(a.dirs or BUILD_DIRS, a.release)
    freshly_built = {i["file"] for i in items}
    held_names = {h.split(":", 1)[0] for h in held}

    # Carry forward what is already live but was not rebuilt in this run.
    if not a.exact:
        previous = _read_json(WEB / "manifest.json", {})
        planned = library_refs()
        for old in previous.get("items", []):
            name = old.get("file", "")
            if not name or name in freshly_built:
                continue
            # Retirement is by plan, not by a missing file: on a cloud runner
            # the mp4s are not in the checkout at all (they live in a Release),
            # so "the file is gone" no longer means anything.
            if old.get("reference") not in planned:
                print(f"  retired {name} ({old.get('reference')} is no longer in "
                      f"library.json)")
                continue
            live = WEB / name
            if not live.exists() and not old.get("release"):
                print(f"  ! dropped {name}: no local file and no release to fetch it from")
                continue
            kept = dict(old)
            if live.exists():
                kept.update(probe(live))
            items.append(kept)
            # Say which of the two it is. "Not rebuilt" and "rebuilt but held
            # back" look identical on the site — the old file stays either way —
            # but they mean very different things to whoever reads the log.
            if name in held_names:
                print(f"  kept {name} (this run's rebuild was held back, so the "
                      f"published version stands)")
            else:
                print(f"  kept {name} (published earlier, not built in this run)")

    # newest first by mtime, so a fresh build lands at the top of the site
    items.sort(key=lambda i: i.get("built_at") or "", reverse=True)

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
    for p in WEB.glob("*.build.json"):
        if p.name.replace(".build.json", ".mp4") not in keep:
            p.unlink()
            print(f"  pruned {p.name} (its clip is retired)")
    if a.prune_posters:
        keep_p = {Path(i["poster"]).name for i in items}
        for p in (WEB / "posters").glob("*.jpg"):
            if p.name not in keep_p:
                p.unlink()

    print(f"[publish] {len(items)} video(s) -> {WEB}")
    for i in items:
        print(f"  {i['file']:20s} {i.get('seconds', 0):6.2f}s  "
              f"{i.get('source', '?')}  [{i.get('topic', '')}]")

    if held:
        print()
        print(f"[publish] {len(held)} clip(s) held back by the gate:", file=sys.stderr)
        for h in held:
            print(f"  {h}", file=sys.stderr)
        # A gated clip means something is wrong upstream, so this run fails
        # loudly rather than quietly publishing a smaller library.
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
