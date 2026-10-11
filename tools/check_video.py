#!/usr/bin/env python3
"""
Hard gate: a rendered clip must pass before it is allowed anywhere near a
release or the site.

This is the seed of the QA layer (Phase 3). It deliberately checks only things
that are mechanically true or false — a video that is silent, truncated, the
wrong shape or too quiet is a defect, not a matter of taste. Nothing here judges
whether the Arabic is correct; that comes from the source pipeline and its
citations, not from a file inspection.

    python3 tools/check_video.py output/video/quran-30-21.mp4 --min-seconds 6

Exit 0 = pass, 1 = fail with the reason on stderr. Every check prints its
measured value, so a pass is evidence rather than an absence of complaints.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return {}


def integrated_loudness(path: Path) -> float | None:
    """EBU R128 integrated loudness in LUFS, or None if it cannot be measured."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True)
    for line in (p.stderr or "").splitlines():
        line = line.strip()
        if line.startswith("I:") and "LUFS" in line:
            try:
                return float(line.split()[1])
            except (IndexError, ValueError):
                pass
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate a rendered clip.")
    ap.add_argument("video")
    ap.add_argument("--min-seconds", type=float, default=5.0)
    ap.add_argument("--max-seconds", type=float, default=180.0)
    ap.add_argument("--expect", default="1080x1920",
                    help="WxH, or 'any' to skip the shape check")
    ap.add_argument("--build-json", default="",
                    help="the matching .build.json; duration is cross-checked")
    ap.add_argument("--loudness", default="-18,-11",
                    help="acceptable integrated loudness range in LUFS")
    ap.add_argument("--require-audio", action="store_true",
                    help="fail if there is no audio stream. A Qur'an clip must have "
                         "its recitation; a silent hadith card is legitimate, so this "
                         "is opt-in rather than the default.")
    a = ap.parse_args(argv)

    video = Path(a.video)
    fails: list[str] = []
    notes: list[str] = []

    if not video.exists():
        print(f"FAIL  no such file: {video}", file=sys.stderr)
        return 1
    size_mb = video.stat().st_size / 1e6
    print(f"file      {video.name}  ({size_mb:.2f} MB)")
    if size_mb < 0.05:
        fails.append(f"file is {size_mb:.3f} MB — a real clip is never this small")

    info = probe(video)
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    au = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        dur = float(info.get("format", {}).get("duration", 0.0))
    except (TypeError, ValueError):
        dur = 0.0

    if v is None:
        fails.append("no video stream")
    else:
        codec = v.get("codec_name")
        shape = f"{v.get('width')}x{v.get('height')}"
        rate = v.get("r_frame_rate", "?")
        pix = v.get("pix_fmt", "?")
        print(f"video     {codec} {shape} {rate} {pix}")
        if codec != "h264":
            fails.append(f"video codec is {codec}, expected h264")
        if a.expect != "any" and shape != a.expect:
            fails.append(f"shape is {shape}, expected {a.expect}")
        if pix != "yuv420p":
            fails.append(f"pixel format is {pix}; players need yuv420p")
        if rate not in ("30/1", "24/1", "25/1", "30000/1001"):
            notes.append(f"unusual frame rate {rate}")

    if au is None:
        msg = "no audio stream"
        if a.require_audio:
            fails.append(msg + " — this clip must carry recitation or narration")
        else:
            # A hadith clip with no recitation and no narration is legitimately
            # silent, so this is a note unless audio was explicitly expected.
            notes.append(msg + " (fine only if the clip is intentionally silent)")
    else:
        print(f"audio     {au.get('codec_name')} {au.get('sample_rate')}Hz "
              f"{au.get('channels')}ch")
        if au.get("codec_name") != "aac":
            fails.append(f"audio codec is {au.get('codec_name')}, expected aac")
        if str(au.get("sample_rate")) != "44100":
            fails.append(f"sample rate is {au.get('sample_rate')}, expected 44100")

    print(f"duration  {dur:.2f}s")
    if dur < a.min_seconds:
        fails.append(f"duration {dur:.2f}s is under the {a.min_seconds:.1f}s floor")
    if dur > a.max_seconds:
        fails.append(f"duration {dur:.2f}s is over the {a.max_seconds:.1f}s ceiling")

    if a.build_json:
        bj = Path(a.build_json)
        if bj.exists():
            try:
                said = float(json.loads(bj.read_text(encoding="utf-8"))["seconds"])
                if abs(said - dur) > 0.5:
                    fails.append(f"build record says {said:.2f}s but the file is "
                                 f"{dur:.2f}s")
                else:
                    print(f"build     record agrees ({said:.2f}s)")
            except Exception as e:
                notes.append(f"could not read the build record: {e}")
        else:
            notes.append(f"no build record at {bj}")

    if au is not None and dur > 0:
        lo, _, hi = a.loudness.partition(",")
        loud = integrated_loudness(video)
        if loud is None:
            notes.append("loudness could not be measured")
        else:
            print(f"loudness  {loud:.1f} LUFS")
            try:
                if not (float(lo) <= loud <= float(hi)):
                    fails.append(f"loudness {loud:.1f} LUFS is outside {lo}..{hi}")
            except ValueError:
                pass

    for n in notes:
        print(f"note      {n}")
    if fails:
        print()
        for f in fails:
            print(f"FAIL      {f}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
