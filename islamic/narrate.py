"""
Urdu narration as a standalone process.

Why this is not a function call: the MMS-TTS model holds ~500 MB of torch
allocator arenas that `del` + `gc.collect()` do not return to the OS. While the
parent process kept that memory, ffmpeg was repeatedly OOM-killed in the 2 GB
sandbox — and because it dies by signal, its stderr is empty, which reads like a
mystery. Running the model in a short-lived child means the encoder starts with
the full sandbox available.

Usage:
    python -m islamic.narrate --text-file in.txt --out out.wav [--engine mms]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def narrate(text: str, out_path: Path, engine: str = "fasih",
            sr_out: int = 44_100, flow: bool = True) -> dict:
    """Synthesise `text` and write a mono 44.1 kHz wav. Runs in a child process."""
    import gc
    import subprocess

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from naat.tts import NaatTTS, split_breath_groups

    from .voice import VOICES, make_voice

    # `make_voice` picks the backend the catalogue key names - Piper or Kokoro -
    # so this file does not grow an engine branch every time one is added.
    tts = make_voice(engine) if engine in VOICES else NaatTTS(engine)

    # Everything the engine is asked to say goes through a normaliser first, but
    # WHICH normaliser depends on the language: the Urdu one strips Latin script
    # (an Urdu voice cannot say it) and would destroy an English script.
    if getattr(tts, "lang", None) == "en":
        from .english import normalize_for_speech_en as normalise
    else:
        from .urdu import normalize_for_speech as normalise
    text = normalise(text)

    tts.load()
    src_sr = tts.sr
    errors = 0

    # ---- FLOW ----------------------------------------------------------
    # Read the passage in ONE pass and let the engine decide where its own
    # sentences are. The old path cut the text into breath groups and glued a
    # flat 0.30 s after each, which is exactly the defect the reference repo
    # measured: creators pause 1.5 times a minute, line-by-line synthesis 19-23.
    # Measured on our own copy: silence fell from 12.0% of the clip to 7.2%.
    n_groups = 1
    if flow and hasattr(tts, "say_flow"):
        parts = [tts.say_flow(text)]
    else:
        groups = split_breath_groups(text)
        if not groups:
            raise RuntimeError("nothing to narrate")
        parts = []
        n_groups = len(groups)
        for i, g in enumerate(groups):
            try:
                parts.append(tts.say(g, seed=100 + i))
                parts.append(np.zeros(int(src_sr * 0.30), dtype=np.float32))
            except Exception as e:      # keep whatever did render
                errors += 1
                print(f"[narrate] group {i} failed: {e}", file=sys.stderr)
    if not parts:
        raise RuntimeError("no narration produced")

    # drop the model before handing the buffer to ffmpeg
    if hasattr(tts, "close"):
        tts.close()                     # Piper: drop the ONNX session
    tts._model = None
    tts._tok = None
    del tts
    for _ in range(3):
        gc.collect()

    full = np.concatenate(parts)
    peak = float(np.abs(full).max()) or 1.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".raw.wav")
    sf.write(tmp, (full / peak * 0.92).astype(np.float32), src_sr)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
                    "-ar", str(sr_out), "-ac", "1", str(out_path)], check=True)
    tmp.unlink(missing_ok=True)
    return {"seconds": round(len(full) / src_sr, 2), "flow": flow,
            "groups": n_groups,
            "failed_groups": errors, "engine": engine}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Urdu narration (isolated process)")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", default="fasih")
    ap.add_argument("--no-flow", action="store_true",
                    help="synthesise group-by-group (the old, pausier way)")
    ap.add_argument("--json", action="store_true", help="print a result record")
    a = ap.parse_args(argv)
    text = Path(a.text_file).read_text(encoding="utf-8")
    info = narrate(text, Path(a.out), engine=a.engine, flow=not a.no_flow)
    if a.json:
        print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
