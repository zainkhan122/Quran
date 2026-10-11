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


def narrate(text: str, out_wav: Path, engine: str = "mms") -> float:
    """Urdu narration -> 44.1 kHz mono wav. Returns its duration."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from naat.tts import NaatTTS, split_breath_groups
    tts = NaatTTS(engine=engine)
    tts.load()
    src_sr = tts.sr
    parts: list[np.ndarray] = []
    for i, g in enumerate(split_breath_groups(text)):
        try:
            parts.append(tts.say(g, seed=200 + i))
            parts.append(np.zeros(int(src_sr * 0.32), dtype=np.float32))
        except Exception as e:
            print(f"  [produce] narration skip: {e}")
    if not parts:
        raise RuntimeError("nothing narrated")
    full = np.concatenate(parts)
    peak = float(np.abs(full).max()) or 1.0
    raw = out_wav.with_suffix(".raw.wav")
    sf.write(raw, (full / peak * 0.93).astype(np.float32), src_sr)
    # free the model before ffmpeg/x264 start (2 GB box)
    tts._model = tts._tok = None
    del tts
    import gc
    gc.collect()
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ar", str(SR), "-ac", "1",
          str(out_wav)])
    raw.unlink(missing_ok=True)
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Produce a professional video.")
    ap.add_argument("--ref", default="quran:30:21",
                    help="quran:S:A or collection:number")
    ap.add_argument("--topic", default="marriage", choices=list_topics())
    ap.add_argument("--out", default="output/video",
                    help="build folder; publish.py reads videos.json + sources.json here")
    ap.add_argument("--engine", default="mms", choices=["mms", "mms-ft", "gtts"])
    ap.add_argument("--no-textures", action="store_true")
    ap.add_argument("--landscape", action="store_true")
    ap.add_argument("--english", action="store_true", help="caption the English too")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args(argv)

    from .topics import get
    t = get(a.topic)
    topic_label_en = t.get("headline", t["label"])["en"]
    topic_label_ur = t.get("headline", t["label"])["ur"]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    kind, _, rest = a.ref.partition(":")

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
        if item.grade and "See a scholar" in item.grade:
            print("  [produce] note: this collection carries a range of grades — "
                  "the citation says so on the frame")

    # ---- 2. narration ----------------------------------------------------
    nar_secs = 0.0
    nar = None
    if item.urdu:
        from .sources import has_isnad
        if item.kind == "hadith" and has_isnad(item.urdu):
            print("  [produce] isnad present — card only, no auto-narration")
        else:
            nar = out / "narration.wav"
            nar_secs = narrate(item.urdu, nar, engine=a.engine)
            print(f"[produce] Urdu narration {nar_secs:.1f}s")

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
        english=(item.english or "") if a.english else "",
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
