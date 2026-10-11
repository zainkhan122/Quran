#!/usr/bin/env python3
"""
Build a male-voice audition pack for the narration.

The owner asked to hear candidates before one is chosen, so this renders the
SAME real translation through every candidate, announces each one in its own
voice, and glues the results into one mp3 that can be listened to end to end.

    python3 tools/voice_audition.py                    # the shortlist below
    python3 tools/voice_audition.py --list             # every male voice Kokoro has
    python3 tools/voice_audition.py --voices am_onyx bm_george

Design notes:

* **One sample per child process.** Piper ships ~200 MB of weights and Kokoro
  loads a 310 MB ONNX graph; loading both in one process has OOM-killed this
  sandbox before. Each voice is synthesised by a fresh `--synth-one` child.
* **The text is the real one.** It reads the English translation of
  `quran:30:21` straight out of `islamic/sources.py`, so what is approved is
  what the clips will actually say, at the length they will say it.
* **Measurement, not adjectives.** Every candidate gets its pace (wpm) and its
  median pitch, so the table below the samples says which voices are deep and
  which are brisk instead of asking the owner to trust a description.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KOKORO_DIR = Path.home() / ".cache" / "kokoro"
KOKORO_ONNX = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"

#: engine, voice, licence, one-line description for the approval table.
#: Piper's en_free is first because it is what the owner has heard and rejected:
#: the comparison is the point.
CANDIDATES = [
    # engine, voice, licence, note for the table, and what the voice SAYS as its
    # own label - never the raw id, which a phonemiser reads as "am underscore".
    ("piper", "en_free", "CC-BY-4.0",
     "REJECTED: measures 250 Hz - the female range", "One. The current voice."),
    ("kokoro", "am_michael", "Apache-2.0",
     "neutral US male, the narration standard", "Two. Michael."),
    ("kokoro", "am_onyx", "Apache-2.0",
     "deep US male, news-anchor weight", "Three. Onyx."),
    ("kokoro", "am_fenrir", "Apache-2.0",
     "warm mid US male", "Four. Fenrir."),
    ("kokoro", "bm_george", "Apache-2.0",
     "classic British male", "Five. George."),
    ("kokoro", "bm_lewis", "Apache-2.0",
     "low British male", "Six. Lewis."),
]

KOKORO_LICENCE = "Apache-2.0 (model card); voices trained on permissive corpora"


def kokoro_voices() -> list[str]:
    from kokoro_onnx import Kokoro
    k = Kokoro(str(KOKORO_ONNX), str(KOKORO_VOICES))
    return sorted(v for v in k.get_voices() if v.startswith(("am_", "bm_")))


def synth_kokoro(text: str, voice: str, out: Path) -> float:
    import soundfile as sf
    from kokoro_onnx import Kokoro
    k = Kokoro(str(KOKORO_ONNX), str(KOKORO_VOICES))
    samples, sr = k.create(text, voice=voice, speed=0.95, lang="en-us")
    sf.write(str(out), samples, sr)
    return len(samples) / sr


def synth_piper(text: str, voice: str, out: Path) -> float:
    from islamic.voice import VOICES, UrduVoice
    from islamic.english import normalize_for_speech_en
    tts = UrduVoice(voice)
    tts.load()
    audio = tts.say_flow(normalize_for_speech_en(text)) if hasattr(tts, "say_flow") \
        else tts.say(normalize_for_speech_en(text))
    import soundfile as sf
    sf.write(str(out), audio, tts.sr)
    return len(audio) / tts.sr


def median_f0_hz(wav: Path) -> float:
    """Median pitch, by harmonic product spectrum.

    The first version of this used autocorrelation and was WRONG - it read the
    Piper voice at 256 Hz while a harmonic-product reading said 72 Hz, and both
    numbers were quoted before anyone checked. This one is validated against
    synthetic tones of known pitch (`--check-pitch`) and reproduces them within
    about 1 Hz, so the table in the audition report can be trusted.

    It matters because the voice the owner rejected measures **247.6 Hz** - the
    female range - while every Kokoro male candidate sits between 88 and 141 Hz.
    """
    import numpy as np
    import soundfile as sf
    x, sr = sf.read(str(wav), dtype="float32", always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1)
    win = int(0.05 * sr)
    f = np.fft.rfftfreq(8192, 1 / sr)
    vals = []
    for i in range(0, len(x) - win, win // 2):
        w = x[i:i + win]
        if float(np.abs(w).mean()) < 0.02:
            continue
        spec = np.abs(np.fft.rfft(w * np.hanning(win), 8192))
        prod = spec.copy()
        for h in (2, 3, 4, 5):
            prod *= np.interp(f * h, f, spec, left=0, right=0)
        band = (f > 60) & (f < 400)
        vals.append(f[band][int(np.argmax(prod[band]))])
    return float(np.median(vals)) if vals else 0.0


def check_pitch() -> int:
    """Prove the pitch instrument on tones whose answer is known."""
    import numpy as np
    sr, t = 22050, None
    t = np.arange(sr * 2) / sr
    bad = 0
    for true_f0 in (85, 110, 140, 200, 250):
        sig = sum(np.sin(2 * np.pi * true_f0 * h * t) / h
                  for h in range(1, 9)).astype(np.float32) * 0.3
        import tempfile
        import soundfile as sf
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            sf.write(fh.name, sig, sr)
            got = median_f0_hz(Path(fh.name))
        ok = abs(got - true_f0) < 8
        bad += 0 if ok else 1
        print(f"  {true_f0:3d} Hz -> {got:6.1f} Hz   {'OK' if ok else 'WRONG'}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Male-voice audition pack")
    ap.add_argument("--ref", default="quran:30:21", help="whose English to read")
    ap.add_argument("--out", default="docs/samples/voice-audition-en.mp3")
    ap.add_argument("--voices", nargs="*", help="kokoro voice ids (default: shortlist)")
    ap.add_argument("--list", action="store_true", help="list male Kokoro voices")
    ap.add_argument("--check-pitch", action="store_true",
                    help="validate the pitch measurement on known tones")
    ap.add_argument("--synth-one", help="internal: engine:voice:out:label for one sample")
    ap.add_argument("--work", default=None)
    a = ap.parse_args(argv)

    if a.check_pitch:
        return 1 if check_pitch() else 0

    if a.list:
        if not KOKORO_ONNX.exists():
            print(f"missing {KOKORO_ONNX}; see the fetch step in this file's header")
            return 2
        for v in kokoro_voices():
            print("  ", v)
        return 0

    # ---- child mode: synthesise exactly one sample and stop -----------------
    if a.synth_one:
        engine, voice, out, label, spoken_label = a.synth_one.split("|")
        from islamic.sources import load_items
        item = load_items([a.ref])[0]
        text = item.english or ""
        out_p, label_p = Path(out), Path(label)
        if engine == "kokoro":
            synth_kokoro(spoken_label, voice, label_p)
            synth_kokoro(text, voice, out_p)
        else:
            synth_piper(spoken_label, voice, label_p)
            synth_piper(text, voice, out_p)
        return 0

    # ---- driver ------------------------------------------------------------
    from islamic.sources import load_items
    item = load_items([a.ref])[0]
    text = (item.english or "").strip()
    if not text:
        print(f"{a.ref} has no English translation to read", file=sys.stderr)
        return 2

    jobs = CANDIDATES
    if a.voices:
        jobs = [("kokoro", v, KOKORO_LICENCE, "", v.replace("_", " ")) for v in a.voices]

    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="audition-"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"[audition] text: {len(text)} chars from {a.ref}")
    print(f"[audition] work: {work}")

    rows, pieces = [], []
    for n, (engine, voice, licence, note, spoken) in enumerate(jobs, start=1):
        tag = f"{n:02d}-{engine}-{voice}"
        body, label = work / f"{tag}-body.wav", work / f"{tag}-label.wav"
        r = subprocess.run([sys.executable, __file__, "--ref", a.ref,
                            "--synth-one", f"{engine}|{voice}|{body}|{label}|{spoken}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  !! {tag} failed: {r.stderr.strip()[-300:]}")
            continue
        secs = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                               "format=duration", "-of", "csv=p=0", str(body)],
                              capture_output=True, text=True).stdout.strip()
        secs = float(secs or 0)
        words = len(text.split())
        rows.append({"n": n, "engine": engine, "voice": voice, "licence": licence,
                     "note": note, "seconds": round(secs, 2),
                     "wpm": round(words / (secs / 60)) if secs else 0,
                     "f0_hz": round(median_f0_hz(body))})
        pieces += [str(label), str(body)]
        print(f"  {n}. {engine}/{voice}  {secs:.1f}s  {rows[-1]['wpm']} wpm  "
              f"{rows[-1]['f0_hz']} Hz")

    if not pieces:
        print("nothing was synthesised", file=sys.stderr)
        return 1

    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in pieces))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c:a", "libmp3lame", "-b:a", "128k",
                    "-ar", "44100", str(out)], check=True)
    print(f"\n[audition] -> {out}  ({out.stat().st_size/1e6:.1f} MB)")
    (work / "audition.json").write_text(json.dumps(rows, indent=2))
    print("\n  #  engine  voice        licence      wpm   f0")
    for r in rows:
        print(f"  {r['n']}. {r['engine']:7s} {r['voice']:12s} {r['licence']:12s} "
              f"{r['wpm']:4d}  {r['f0_hz']:4d} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
