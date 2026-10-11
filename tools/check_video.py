#!/usr/bin/env python3
"""
Hard gate: a rendered clip must pass before it reaches a release or the site.

Two kinds of check live here, and they are deliberately kept apart.

**File checks** are mechanical properties of the artefact: container, codec,
pixel format, shape, duration, loudness. A clip that is silent, truncated, the
wrong shape or too quiet is a defect, not a matter of taste.

**Correctness checks** read the build record (`<slug>.build.json`) and re-assert
the promises this project is built on, at the last moment before publishing —
after rendering, after upload, after a parallel runner has had every chance to
produce something slightly different from what was intended:

  * the clip carries a citation (reference + human-readable source);
  * the sacred text on it is present and non-empty;
  * a Qur'an clip names its reciter and the source of its word timings. This is
    the one that matters most: the whole project promises real recitation, and a
    missing reciter is the fingerprint of the TTS fallback having fired;
  * the collection is on TRUSTED_COLLECTIONS;
  * a hadith carries a grade line, because the frame always shows one.

Nothing here judges whether the Arabic is *correct* — that is the source
pipeline's job and it is enforced upstream by fetching verbatim and refusing
anything that does not validate. This is the last cheap net before publication.

    python3 tools/check_video.py web/video/quran-30-21.mp4 \
        --build-json output/video/quran-30-21.build.json --require-audio

Exit 0 = pass, 1 = fail with the reason on stderr. Every check prints its
measured value, so a pass is evidence rather than an absence of complaints.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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


def count_words(text: str) -> int:
    """How many words a verse's text contains, ignoring punctuation.

    A naive `len(text.split())` is wrong, and wrong in a way that matters. The
    Uthmani text separates two kinds of token that are not words:

      * waqf marks — `ۚ  2:275 has five of them, so the verse is 45 words and 50
        whitespace tokens;
      * the verse-number marker in some editions.

    A word is a token that contains at least one LETTER. That is a Unicode
    property, not a hand-written range, so it holds for any script the pipeline
    ever fetches rather than only for the samples it was tested on.

    Counting this way turns the check below into a genuine cross-source test: the
    renderer's word count comes from quran.com's `audio.segments`, while the text
    is fetched from alquran.cloud, so agreement means two independent publishers
    say the ayah has the same number of words — and that the word-by-word reveal
    cannot be silently dropping one.
    """
    return sum(1 for tok in text.split()
               if any(unicodedata.category(ch).startswith("L") for ch in tok))


def correctness_failures(build: dict) -> list[str]:
    """Re-assert the project's promises from the build record.

    Returns a list of failures. An empty build record is itself a failure: a clip
    with no record cannot be shown to carry a citation, and unverifiable is not
    the same as fine.
    """
    bad: list[str] = []
    if not build:
        return ["no build record — the clip's citation cannot be verified"]

    ref = (build.get("reference") or "").strip()
    source = (build.get("source") or "").strip()
    kind = (build.get("kind") or "").strip()
    arabic = (build.get("arabic") or "").strip()

    if not ref:
        bad.append("build record has no reference")
    if not source:
        bad.append("build record has no human-readable source (the citation the "
                   "viewer sees)")

    if ref:
        collection = ref.split(":", 1)[0]
        try:
            from islamic.sources import TRUSTED_COLLECTIONS
            if collection not in TRUSTED_COLLECTIONS and collection != "quran":
                bad.append(f"'{collection}' is not on TRUSTED_COLLECTIONS")
        except Exception as e:                       # pragma: no cover
            bad.append(f"could not load TRUSTED_COLLECTIONS: {e}")

    if kind in ("quran", "hadith") and not arabic:
        bad.append(f"a {kind} clip with no Arabic text in its build record")

    if kind == "quran":
        # The central promise. Qur'anic audio is a real recitation, never
        # synthesised speech, and the word timings come from the same source.
        if not (build.get("reciter") or "").strip():
            bad.append("Qur'an clip names no reciter — real recitation is the "
                       "promise; a missing reciter means the TTS fallback fired")
        if not (build.get("timings_source") or "").strip():
            bad.append("Qur'an clip has no timings_source — word-level sync "
                       "cannot be evidenced")

    if kind == "hadith" and not (build.get("grade") or "").strip():
        bad.append("hadith clip carries no grade line, and the frame always "
                   "shows one")

    # A word-by-word clip should account for every word it shows.
    wc = build.get("word_count")
    if kind == "quran" and isinstance(wc, int) and wc > 0 and arabic:
        shown = count_words(arabic)
        if wc < shown:
            bad.append(
                f"the recitation is timed for {wc} words but the text has {shown} — "
                f"the word-by-word reveal would drop {shown - wc} of them")
        elif wc > shown:
            bad.append(
                f"the recitation is timed for {wc} words but the text has only "
                f"{shown} — these timings are for a different text")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate a rendered clip.")
    ap.add_argument("video")
    ap.add_argument("--min-seconds", type=float, default=5.0)
    ap.add_argument("--max-seconds", type=float, default=180.0)
    ap.add_argument("--expect", default="1080x1920",
                    help="WxH, or 'any' to skip the shape check")
    ap.add_argument("--build-json", default="",
                    help="the matching .build.json; citation and loudness checks "
                         "run when it is given. Defaults to the sibling file.")
    ap.add_argument("--loudness", default="-18,-11",
                    help="acceptable integrated loudness range in LUFS")
    ap.add_argument("--require-audio", action="store_true",
                    help="fail if there is no audio stream. A Qur'an clip must have "
                         "its recitation; a silent hadith card is legitimate, so "
                         "this is opt-in rather than the default.")
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

    # ---- the build record: citation and promises --------------------------
    bj = Path(a.build_json) if a.build_json else video.with_suffix(".build.json")
    build: dict = {}
    if bj.exists():
        try:
            build = json.loads(bj.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            fails.append(f"build record is unreadable: {e}")
    else:
        notes.append(f"no build record at {bj}")

    if build:
        print(f"citation  {build.get('reference', '?')} — {build.get('source', '?')}")
        said = build.get("seconds")
        try:
            said = float(said)
            if abs(said - dur) > 0.5:
                fails.append(f"build record says {said:.2f}s but the file is "
                             f"{dur:.2f}s")
            else:
                print(f"build     record agrees ({said:.2f}s)")
        except (TypeError, ValueError):
            notes.append("build record has no usable duration to cross-check")

    for c in correctness_failures(build):
        fails.append(c)

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
