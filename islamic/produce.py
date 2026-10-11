"""
Producer CLI - the professional path.

    python -m islamic.produce --ref quran:30:21 --topic marriage
    python -m islamic.produce --topic daughters --ref quran:81:8
    python -m islamic.produce --ref quran:30:21 --no-textures --landscape

Builds: word-level Arabic with real recitation -> Urdu translation narration,
on generated Islamic ornament, with a compact explanatory topic header and an
easy-to-read citation. Text is always fetched verbatim (see sources.py).
"""

from __future__ import annotations

import argparse
import json
import time
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from .sources import ContentError, hadith, quran
from .studio import Comp, render
from .timings import download_recitation, words_with_timings
from .topics import list_topics

SR = 44_100


def _dur(p: Path) -> float:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True,
                       text=True).stdout.strip()
    try:
        return float(o)
    except ValueError:
        return 0.0


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg: {p.stderr[-1200:]}")


#: Piper `fasih` - MIT, 63 MB, RTF 0.08, male. See islamic/voice.py for the
#: measurement that made this the default over the CC-BY-NC VITS model.
DEFAULT_ENGINE = "fasih"


def narrate(text: str, out_wav: Path, engine: str = DEFAULT_ENGINE) -> float:
    """Urdu narration -> 44.1 kHz mono wav. Returns its duration.

    Runs in a SEPARATE process (islamic/narrate.py). In-process synthesis was the
    cause of a silent, unreproducible failure: after the model is dropped,
    `del` + `gc.collect()` frees about 484 MB of torch memory back to the Python
    process but NOT to the OS, and ffmpeg - which needs the bulk of a 2 GB box to
    encode 1080x1920 - was then killed. A signal death produces no stderr at all,
    so the video simply failed with an empty error. A child process that exits
    after writing the wav hands the whole box back before encoding starts.
    """
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    txt = out_wav.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "islamic.narrate", "--text-file", str(txt),
         "--out", str(out_wav), "--engine", engine],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent))
    txt.unlink(missing_ok=True)

    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(
            "Urdu narration failed (islamic.narrate). "
            "Check that 'bash setup.sh --check' reports torch and transformers.\n"
            + proc.stderr.strip()[-700:])

    skipped = [l for l in proc.stderr.splitlines() if "group" in l and "failed" in l]
    for l in skipped:
        print(f"  [produce] narration {l.strip()}")
    return _dur(out_wav)


def build_audio(rec: Path | None, narration: Path | None, lead: float, phase1: float,
                phase2: float, out: Path, nar_phase: int = 2) -> float:
    """Lay recitation and narration onto one timeline matching the video.

    nar_phase decides where the Urdu narration begins: phase 2 for Qur'an (after
    the recitation finishes) and phase 1 for hadith (under the Arabic, because
    there is no recitation to listen to).
    """
    total = phase1 + phase2
    n = int(total * SR) + SR
    track = np.zeros(n, dtype=np.float64)

    if rec and rec.exists():
        x, sr = sf.read(rec, dtype="float64", always_2d=True)
        x = x.mean(axis=1)
        if sr != SR:
            import scipy.signal as sps
            x = sps.resample_poly(x, SR, sr)
        i = int(lead * SR)
        j = min(i + len(x), n)
        track[i:j] += x[: j - i] * 0.98
    if narration and narration.exists():
        x, sr = sf.read(narration, dtype="float64", always_2d=True)
        x = x.mean(axis=1)
        if sr != SR:
            import scipy.signal as sps
            x = sps.resample_poly(x, SR, sr)
        i = int(((lead if nar_phase == 1 else phase1) + 0.25) * SR)
        j = min(i + len(x), n)
        track[i:j] += x[: j - i] * 0.92

    peak = float(np.abs(track).max()) or 1.0
    sf.write(out, (track / peak * 0.95).astype(np.float32), SR)
    return _dur(out)


def build_parser() -> argparse.ArgumentParser:
    """The CLI, as its own function so `tests/` can assert the defaults.

    Two of those defaults are owner instructions - the voice reads ENGLISH, and
    the card carries both translations - and a default that quietly flips back
    would only be noticed after a clip shipped.
    """
    ap = argparse.ArgumentParser(description="Produce a professional video.")
    ap.add_argument("--ref", default="quran:30:21",
                    help="quran:S:A or collection:number")
    ap.add_argument("--topic", default="marriage", choices=list_topics())
    ap.add_argument("--out", default="output/video",
                    help="build folder; publish.py reads videos.json + sources.json here")
    ap.add_argument("--narrate", default="english", choices=["english", "urdu"],
                    help="which language the VOICE speaks. The card shows both "
                         "either way; this only picks what is read aloud.")
    # Listed from the catalogue so a new voice cannot be added and then be
    # unreachable from the CLI. The VITS engines (mms, mms-ft, gtts) are not in
    # VOICES, so they are appended by hand.
    from .voice import VOICES
    ap.add_argument("--engine", default=None,
                    choices=[*VOICES, "mms", "mms-ft", "gtts"],
                    help="en_michael = Kokoro English (Apache-2.0, the approved "
                         "narration voice); en_onyx/en_george/en_lewis = the "
                         "other approved candidates; en_free = the LibriTTS-R "
                         "voice this replaced, which measures 248 Hz and is "
                         "female despite the name; fasih/aegis = Piper Urdu "
                         "(MIT); en = lessac (research licence, A/B only). "
                         "Default follows --narrate.")
    ap.add_argument("--no-textures", action="store_true")
    ap.add_argument("--landscape", action="store_true")
    # The card carries BOTH translations and the voice reads the English - the
    # owner's instruction. So the English caption is on by default and
    # `--no-english` is the escape hatch for an Urdu-only card.
    ap.add_argument("--english", action=argparse.BooleanOptionalAction,
                    default=True, help="caption the English translation (default on)")
    ap.add_argument("--fps", type=int, default=30)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)

    from .topics import get
    t = get(a.topic)
    topic_label_en = t.get("headline", t["label"])["en"]
    topic_label_ur = t.get("headline", t["label"])["ur"]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kind, _, rest = a.ref.partition(":")

    # ---- 0. authenticity gate (islamic/verify.py) --------------------------
    # Before anything is fetched or rendered, for Qur'an and hadith alike, and
    # fail closed - there is no flag that skips it. A Qur'an ref must agree
    # letter-for-letter across two independent sources; a hadith must be graded
    # sahih or hasan with no grader dissenting.
    from .verify import require
    verdict = require(a.ref)
    print(f"[produce] authenticity: PASS - {verdict.grade_line}")

    # ---- 1. verbatim text + citation -------------------------------------
    if kind == "quran":
        item = quran(rest, topic=topic_label_en)[0]
        words, audio_url = words_with_timings(rest)
        rec = download_recitation(audio_url, out / f"rec_{rest.replace(':','_')}.mp3")
        print(f"[produce] {item.source} · {len(words)} words with real timings")
        rec_secs = _dur(rec)
    else:
        item = hadith(kind, int(rest), topic=topic_label_en)
        words, rec, rec_secs = [], None, 0.0
        print(f"[produce] {item.source} ({item.grade})")

    # ---- 2. narration ----------------------------------------------------
    from .english import for_display
    from .voice import default_voice
    lang = "en" if a.narrate == "english" else "ur"
    engine = a.engine or default_voice(lang)
    script = (item.english if lang == "en" else item.urdu) or ""
    if lang == "en" and not script:
        raise SystemExit(
            f"no English text on {item.reference}; this edition has no English "
            f"translation, so --narrate english cannot read anything")

    nar_secs = 0.0
    nar = None
    if script:
        from .sources import has_isnad
        if item.kind == "hadith" and lang == "ur" and has_isnad(item.urdu):
            print("  [produce] isnad present — card only, no auto-narration")
        else:
            nar = out / "narration.wav"
            nar_secs = narrate(script, nar, engine=engine)
            label = "English" if lang == "en" else "Urdu"
            print(f"[produce] {label} narration {nar_secs:.1f}s (voice {engine})")

    # ---- 3. timeline -----------------------------------------------------
    lead, tail = 0.9, 1.6
    if words:
        # Qur'an: the recitation owns phase 1, the Urdu translation follows it
        phase1 = lead + rec_secs + 1.1
        phase2 = (nar_secs + 1.6) if nar_secs else 7.0
        read_time = len(item.urdu or "") / 12.0
        phase2 = max(phase2, min(read_time, 26.0) + 2.0)
        nar_phase = 2
    else:
        # Hadith: no recitation exists, so the narration sits under the Arabic
        # and the translation gets its own quiet beat to be read.
        phase1 = max(nar_secs + 2.2, 7.0) if nar_secs else 8.0
        phase2 = max(len(item.urdu or "") / 11.0 + 2.5, 7.0)
        nar_phase = 1

    comp = Comp(
        width=1920 if a.landscape else 1080,
        height=1080 if a.landscape else 1920,
        fps=a.fps,
        topic_en=topic_label_en,
        topic_ur=topic_label_ur,
        reference_en=item.source,
        reference_ar=item.source_ar,
        # a grade line belongs on a hadith; "Quran" under "Qur'an 30:21" is noise
        grade=(item.grade or "") if item.kind == "hadith" else "",
        arabic_words=words,
        body_arabic=item.arabic if not words else "",
        urdu=item.urdu or "",
        # for_display, not the raw string: the card must not draw a missing
        # glyph box where the honouring of the Prophet should be.
        english=for_display(item.english or "") if a.english else "",
        phase1=phase1, phase2=phase2, lead=lead, tail=tail,
        textures=not a.no_textures,
        topic_key=a.topic,
    )

    audio = out / "timeline.wav"
    build_audio(rec, nar, lead, phase1, phase2, audio, nar_phase=nar_phase)

    stem = a.ref.replace(":", "-")
    video = out / f"{stem}.mp4"
    print(f"[produce] rendering {comp.total:.1f}s at {comp.width}x{comp.height}@{comp.fps}")
    info = render(comp, audio, video, work=out)
    info.update({"reference": item.reference, "source": item.source,
                 "source_ar": item.source_ar, "grade": item.grade,
                 "topic": topic_label_en, "topic_ur": topic_label_ur,
                 "kind": item.kind,
                 # Which voice read it, in the artefact's own record. English is
                 # the default narration language now, and a build that does not
                 # say so is a build nobody can check afterwards.
                 "narration": {"language": "English" if lang == "en" else "Urdu",
                               "voice": engine if nar_secs else "",
                               "seconds": round(nar_secs, 2)},
                 "reciter": "Mishary Rashid Alafasy" if words else "",
                 "timings_source": "api.quran.com v4 audio.segments" if words else "",
                 "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "pipeline": "islamic.studio (measured-ink layout, word-level reveal)",
                 "arabic": item.arabic, "urdu": item.urdu,
                 "english": item.english,
                 "word_count": len(words)})
    (out / f"{stem}.build.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[produce] -> {video}  {info['seconds']}s  {info['size_mb']} MB")

    # merge into the cumulative index the web manifest reads
    idx_path = out / "videos.json"
    idx = {}
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
        except Exception:
            idx = {}
    idx[video.name] = item.reference
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")

    srcs_path = out / "sources.json"
    srcs = []
    if srcs_path.exists():
        try:
            srcs = json.loads(srcs_path.read_text(encoding="utf-8"))
        except Exception:
            srcs = []
    by_ref = {s.get("reference"): s for s in srcs}
    from dataclasses import asdict
    by_ref[item.reference] = asdict(item)
    srcs_path.write_text(json.dumps(list(by_ref.values()), ensure_ascii=False, indent=2),
                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ContentError as e:
        print(f"content error: {e}", file=sys.stderr)
        sys.exit(2)
