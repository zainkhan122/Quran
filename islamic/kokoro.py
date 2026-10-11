"""
Kokoro-82M: the English narration voice.

Why we left Piper for English
-----------------------------
Piper is a 2023 VITS model and its English output was rejected by the owner on
hearing it: *"TTS is very bad for English. use male sound."* Both halves of that
turned out to be measurable, and one of them was our error:

* The voice we shipped as the English default, `en_US-libritts_r-medium`
  speaker 60, is catalogued male and **measures 248-250 Hz** - the female range.
  No amount of tuning a VITS voice fixes a wrong speaker.
* Kokoro-82M is the current generation of small open TTS, and its male voices
  measure 88-141 Hz.

The comparison, on this box, with the clips we would actually ship:

    engine / voice              licence      download   size    RTF
    piper en_US-libritts_r      CC-BY-4.0      63 MB    63 MB   0.15
    kokoro am_michael           Apache-2.0     353 MB   353 MB  0.86

RTF 0.86 means a 20 s narration synthesises in ~17 s. That is five times slower
than Piper and it is still far inside the budget, because narration already runs
in its own child process (`islamic/narrate.py`) - the 353 MB graph is loaded,
used, and dropped before ffmpeg starts.

The licence is the other half: Apache-2.0, model and voicepack together, so a
monetised channel can ship it with no asterisk.

What this does NOT fix
----------------------
Nothing about Urdu. Kokoro's 82M multilingual checkpoints do not cover Urdu,
and Urdu narration was retired anyway (the voice reads English; Urdu stays on
the card as text).

Usage:
    python3 -m islamic.kokoro --text "..." --out /tmp/a.wav [--voice am_michael]
    python3 -m islamic.kokoro --check
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:                   # numpy stays optional at import time
    import numpy as np

#: Model + voicepack, from the kokoro-onnx release that pairs them. Pinned to
#: v1.0 on purpose: `main` is not a version and this pipeline has to be
#: reproducible months later from a resume note.
_BASE = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
         "model-files-v1.0")
MODEL_FILE = "kokoro-v1.0.onnx"
VOICES_FILE = "voices-v1.0.bin"

#: Excluded from the workspace snapshot (it is under ~/.cache), so a 353 MB
#: download does not count against the repo budget.
CACHE = Path.home() / ".cache" / "kokoro"


class KokoroError(RuntimeError):
    pass


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {dest.name}  {pct:3d}%  ({done >> 20}/{total >> 20} MB)",
                      end="", file=sys.stderr)
    print("", file=sys.stderr)
    tmp.replace(dest)


def fetch(cache: Path | None = None) -> tuple[Path, Path]:
    """Return (model, voices) paths, downloading once into the cache."""
    d = cache or CACHE
    model, voices = d / MODEL_FILE, d / VOICES_FILE
    for p in (model, voices):
        if not p.exists():
            _download(f"{_BASE}/{p.name}", p)
    return model, voices


def installed(cache: Path | None = None) -> bool:
    d = cache or CACHE
    return (d / MODEL_FILE).exists() and (d / VOICES_FILE).exists()


def lang_for(voice_id: str) -> str:
    """Kokoro packs British and American voices in one file and wants the
    language spelled out: `bm_*` is en-gb, `am_*` is en-us."""
    return "en-gb" if voice_id.startswith("b") else "en-us"


class KokoroVoice:
    """Kokoro behind the same interface as `UrduVoice`.

    `say()` returns float32 mono at `self.sr`, so nothing downstream needs to
    know which engine ran - the same contract Piper is behind.
    """

    def __init__(self, key: str, spec: dict, cache: Path | None = None):
        self.voice = key                        # the catalogue key, e.g. en_michael
        self.voice_id = spec["voice_id"]        # the pack's id, e.g. am_michael
        self.spec = spec
        self.cache = cache
        self._k = None
        self.sr = 24_000

    @property
    def lang(self) -> str:
        return self.spec.get("lang", "en")

    @property
    def licence(self) -> str:
        return self.spec["licence"]

    @property
    def gender(self) -> str:
        return self.spec.get("gender", "")

    @property
    def test_only(self) -> bool:
        return bool(self.spec.get("test_only"))

    def load(self) -> "KokoroVoice":
        if self._k is not None:
            return self
        try:
            from kokoro_onnx import Kokoro
        except ImportError as e:                      # pragma: no cover
            raise KokoroError(
                "kokoro-onnx is not installed. `bash setup.sh` installs it; "
                "for a one-off: pip install kokoro-onnx") from e
        model, voices = fetch(self.cache)
        self._k = Kokoro(str(model), str(voices))
        return self

    def say_flow(self, text: str, **_: object) -> "np.ndarray":  # noqa: F821
        """Read the whole passage in one pass.

        Same principle as the Piper path (see `UrduVoice.say_flow`): the engine
        does the sentence segmentation, because it is the thing that knows
        where the sentences are, and we do not glue a fixed silence after each
        one. `Kokoro.create` splits long text internally and concatenates, so
        this is already flow reading - there is no `JOIN_SENTENCE` here because
        there is nothing for us to top up.
        """
        return self.say(text)

    def say(self, text: str, seed: int | None = None) -> "np.ndarray":  # noqa: F821
        """One pass -> float32 mono waveform.

        `seed` is accepted and ignored for drop-in compatibility: the exported
        ONNX graph is deterministic, so there is no sampling noise to control.
        """
        del seed
        import numpy as np
        self.load()
        samples, sr = self._k.create(text, voice=self.voice_id,
                                     speed=float(self.spec.get("speed", 1.0)),
                                     lang=lang_for(self.voice_id))
        self.sr = int(sr)
        if samples is None or not len(samples):
            raise KokoroError(f"voice produced no audio for {text[:40]!r}")
        return np.asarray(samples, dtype=np.float32)

    def close(self) -> None:
        """Drop the graph. ffmpeg runs next and wants the memory."""
        self._k = None

    def describe(self) -> dict:
        return {"engine": "kokoro", "voice": self.voice, "voice_id": self.voice_id,
                "lang": self.lang, "gender": self.gender, "licence": self.licence,
                "test_only": self.test_only, "sample_rate": self.sr,
                "speed": self.spec.get("speed", 1.0),
                "measured_f0_hz": self.spec.get("measured_f0_hz")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kokoro narration (isolated process)")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out")
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--check", action="store_true",
                    help="report whether the model is cached")
    a = ap.parse_args(argv)

    if a.check:
        if installed():
            d = CACHE
            print(f"kokoro: cached at {d} "
                  f"({(d / MODEL_FILE).stat().st_size // 1_000_000} MB + "
                  f"{(d / VOICES_FILE).stat().st_size // 1_000_000} MB)")
            return 0
        print(f"kokoro: NOT cached (expected in {CACHE}); "
              f"python3 -m islamic.kokoro --fetch")
        return 1

    if a.out and (a.text or a.text_file):
        import soundfile as sf
        from islamic.voice import VOICES, make_voice
        text = a.text or Path(a.text_file).read_text(encoding="utf-8")
        # find the catalogue key whose voice_id matches, so the licence and the
        # correction to the catalogue's pitch table travel with the audio
        key = next((k for k, v in VOICES.items()
                    if v.get("engine") == "kokoro" and v.get("voice_id") == a.voice),
                   None)
        tts = make_voice(key) if key else KokoroVoice(
            a.voice, {"voice_id": a.voice, "lang": "en", "licence": "Apache-2.0"})
        audio = tts.say_flow(text)
        sf.write(a.out, audio, tts.sr)
        print(f"{a.voice}: {len(audio) / tts.sr:.2f}s -> {a.out}")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
