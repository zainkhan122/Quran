"""
The Urdu narration voice.

Why Piper and not the VITS model we started with
------------------------------------------------
The published Tacotron-vs-MMS benchmark (Interspeech 2025) puts Urdu at
WER 13.1% for Tacotron against 25.6% for Meta MMS, and it reports that MMS fails
outright on digits and symbols. That was the reason to look, but the reasons to
move are measurable here, on this box, with the voices we would actually ship:

    voice                     licence        size     load    RTF    WER*
    facebook/mms-tts-urd-...  CC-BY-NC-4.0   145 MB   3.8 s   0.51   26.6%
    piper ur_PK-fasih (m)     MIT             63 MB   2.1 s   0.08   26.6%
    piper ur_PK-aegis (f)     MIT             63 MB   1.8 s   0.08   22.8%

    * three real sentences of our own copy, transcribed back with whisper-base.
      Read that column with suspicion: all three land within 4 points of each
      other, which means the ASR is the floor, not the voices. It is recorded
      because it is honest, not because it decides anything.

The licence does decide something. **CC-BY-NC is non-commercial.** A channel
that is monetised, or might be, cannot ship narration under it, and that is not
a quality trade-off - it is a hard stop. Both Piper Urdu voices are MIT.

The speed decides the rest: 0.08 RTF means a one-minute narration is synthesised
in under five seconds, and the model is 63 MB of ONNX rather than 500 MB of
torch allocator arenas. On a 2 GB sandbox with ffmpeg next in the pipeline, that
is the difference between a render that fits and one that gets OOM-killed.

What this does NOT fix
----------------------
Neither voice is *diacritized*, and Urdu text without short vowels is
under-specified - the engine is guessing at vowel sounds it cannot see. That is
the real reason Urdu TTS sounds robotic, and it is a property of the input, not
of the model. `islamic/urdu.py` does the half of the job that is free and
determinate (markers, digits, punctuation, script). The other half - actually
restoring the harakat - needs a diacritization model, which is not in the CPU
budget. See RESEARCH.md.

Usage:
    python3 -m islamic.voice --text "السلام علیکم" --out /tmp/a.wav
    python3 -m islamic.voice --list
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:                   # numpy stays optional at import time
    import numpy as np

#: Every voice the studio can speak with. `rel` is the path inside
#: rhasspy/piper-voices; `speaker` is required for multi-speaker models.
#:
#: Licences were read off each voice's MODEL_CARD, at the source, because a
#: third-party listing already lied to us once about Fasih. `test_only` marks a
#: voice that sounds good but whose licence we have not cleared for a monetised
#: channel - it is fine for an A/B, not for a published clip.
VOICES: dict[str, dict] = {
    # -- Urdu ---------------------------------------------------------------
    "fasih": {"rel": "ur/ur_PK/fasih/medium/ur_PK-fasih-medium",
              "lang": "ur", "gender": "male", "licence": "MIT"},
    "aegis": {"rel": "ur/ur_PK/aegis_female/medium/ur_PK-aegis_female-medium",
              "lang": "ur", "gender": "female", "licence": "MIT"},
    # -- English ------------------------------------------------------------
    # Lessac is the canonical Piper English voice and the best of the free ones
    # by common report, but its MODEL_CARD points at the Blizzard 2013 research
    # licence - so it is the *test* voice, not the shippable one.
    "en": {"rel": "en/en_US/lessac/medium/en_US-lessac-medium",
           "lang": "en", "gender": "male",
           "licence": "Blizzard 2013 Lessac (research)", "test_only": True,
           # measured: 227 wpm at the model default, 179 wpm at 1.4, against a
           # creators' median of 184.5. Narration wants the slower of the two.
           "length_scale": 1.4},
    # LibriTTS-R: 904 speakers, CC BY 4.0, clear for commercial use. Speaker 60
    # is a low male id chosen from the model's own speaker map.
    # CORRECTED. This was catalogued male and shipped as the English default.
    # It measures 248-250 Hz, which is the female range, and that is what the
    # owner heard when they said the English TTS was "very bad". The catalogue
    # was wrong, not their ear. It stays for the A/B and must never be a
    # default again - `tests/test_voice.py` now checks declared gender against
    # the measured pitch so this cannot be mislabelled twice.
    "en_free": {"rel": "en/en_US/libritts_r/medium/en_US-libritts_r-medium",
                "lang": "en", "gender": "female", "licence": "CC-BY-4.0",
                "speaker": 60, "length_scale": 1.60, "measured_f0_hz": 248},
    # -- Kokoro-82M: the English narration voices ---------------------------
    # Apache-2.0 for the model AND the voicepack. 353 MB, RTF 0.86 on this box,
    # and it runs in the narration child process so ffmpeg still gets its RAM.
    # `speed` is Kokoro's own control; 0.95 measures 177 wpm against the
    # study's creators' median of 184.5 - already the right pace, so there is
    # no length_scale to tune. The F0 figures are measured, not quoted from a
    # model card, and are what the owner chose between.
    "en_michael": {"engine": "kokoro", "voice_id": "am_michael", "lang": "en",
                   "gender": "male", "licence": "Apache-2.0", "speed": 0.95,
                   "measured_f0_hz": 117},
    "en_onyx": {"engine": "kokoro", "voice_id": "am_onyx", "lang": "en",
                "gender": "male", "licence": "Apache-2.0", "speed": 0.88,
                "measured_f0_hz": 88},
    "en_fenrir": {"engine": "kokoro", "voice_id": "am_fenrir", "lang": "en",
                  "gender": "male", "licence": "Apache-2.0", "speed": 0.95,
                  "measured_f0_hz": 141},
    "en_george": {"engine": "kokoro", "voice_id": "bm_george", "lang": "en",
                  "gender": "male", "licence": "Apache-2.0", "speed": 1.0,
                  "measured_f0_hz": 132},
    "en_lewis": {"engine": "kokoro", "voice_id": "bm_lewis", "lang": "en",
                 "gender": "male", "licence": "Apache-2.0", "speed": 0.95,
                 "measured_f0_hz": 91},
}
DEFAULT_VOICE = "fasih"
#: The owner heard the candidates and chose this one (2026-10-11):
#: "2 - Michael". Kokoro am_michael, Apache-2.0, 117 Hz. Everything before it
#: was either the wrong speaker (en_free measures 248 Hz - female) or a
#: research licence (lessac). See `tools/voice_audition.py` for the pack that
#: was approved and `docs/samples/voice-audition-en.mp3` for the audio.
DEFAULT_EN_VOICE = "en_michael"


def make_voice(key: str, cache: Path | None = None):
    """Build the engine a catalogue key names.

    Two backends now sit behind one key space: Piper (ONNX, cheap, Urdu) and
    Kokoro (ONNX, modern, English). Callers ask for a *voice*, not an engine
    class, so adding the next engine does not touch `narrate.py` or
    `produce.py`.
    """
    if key not in VOICES:
        raise VoiceError(f"unknown voice {key!r}; have: {', '.join(VOICES)}")
    spec = VOICES[key]
    if spec.get("engine") == "kokoro":
        from .kokoro import KokoroVoice
        return KokoroVoice(key, spec, cache=cache)
    return UrduVoice(key, cache=cache)


def voices_for(lang: str) -> list[str]:
    return [k for k, v in VOICES.items() if v.get("lang") == lang]


def default_voice(lang: str) -> str:
    return DEFAULT_VOICE if lang == "ur" else DEFAULT_EN_VOICE

_HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_CACHE = Path.home() / ".cache" / "urdu-voice"


class VoiceError(RuntimeError):
    pass


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, tmp.open("wb") as fh:
        while chunk := r.read(1 << 20):
            fh.write(chunk)
    tmp.replace(dest)


def fetch(voice: str = DEFAULT_VOICE, cache: Path | None = None) -> tuple[Path, Path]:
    """Return (onnx, config) paths, downloading once into the cache."""
    if voice not in VOICES:
        raise VoiceError(f"unknown voice {voice!r}; have: {', '.join(VOICES)}")
    rel = VOICES[voice]["rel"]
    d = cache or _CACHE
    onnx = d / f"{Path(rel).name}.onnx"
    cfg = d / f"{Path(rel).name}.onnx.json"
    for p, ext in ((onnx, "onnx"), (cfg, "onnx.json")):
        if not p.exists():
            _download(f"{_HF}/{rel}.{ext}", p)
    return onnx, cfg


#: Sentence-ending punctuation, both scripts. What remains is a clause break.
_SENT_END = "۔؟!.…"


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith(tuple(_SENT_END))


def _chunk_ends_sentence(chunk) -> bool:
    """Did this chunk end a sentence, or just a clause?

    The chunk carries no text, but it does carry its phonemes, and eSpeak keeps
    the punctuation in them: a chunk that ended on ۔ comes back ending in "."
    and one that ended on ، comes back ending in ",". So the engine tells us
    which kind of break it made, and we do not have to guess by re-parsing.
    """
    ph = "".join(getattr(chunk, "phonemes", None) or [])
    return ph.rstrip().endswith((".", "!", "?", "…"))


def _tail_silence(audio: "np.ndarray", sr: int, thresh_db: float = -42.0) -> float:  # noqa: F821
    """Seconds of quiet the model itself left at the end of a chunk.

    Topping up rather than appending is the difference between a consistent
    pause and a pause that is 0.30 s plus whatever the model happened to leave.
    """
    import numpy as np
    if not len(audio):
        return 0.0
    n = max(int(sr * 0.01), 1)
    frames = len(audio) // n
    if frames < 2:
        return 0.0
    rms = np.sqrt((audio[: frames * n].reshape(frames, n).astype(np.float64) ** 2).mean(axis=1))
    peak = rms.max() or 1.0
    floor = peak * 10 ** (thresh_db / 20)
    quiet = rms < floor
    run = 0
    for q in quiet[::-1]:
        if not q:
            break
        run += 1
    return run * n / sr


class UrduVoice:
    """A Piper voice behind the same interface the rest of the pipeline uses.

    `say()` returns float32 mono at `self.sr`, exactly like the VITS engine it
    replaces, so nothing downstream has to know which one ran.
    """

    def __init__(self, voice: str = DEFAULT_VOICE, cache: Path | None = None,
                 threads: int = 2):
        if voice not in VOICES:
            raise VoiceError(f"unknown voice {voice!r}; have: {', '.join(VOICES)}")
        self.voice = voice
        self.cache = cache
        self.threads = threads
        self._pv = None
        self.sr = 22_050

    @property
    def spec(self) -> dict:
        return VOICES[self.voice]

    @property
    def lang(self) -> str:
        return self.spec.get("lang", "ur")

    @property
    def licence(self) -> str:
        return self.spec["licence"]

    @property
    def gender(self) -> str:
        return self.spec.get("gender", "")

    @property
    def test_only(self) -> bool:
        return bool(self.spec.get("test_only"))

    def load(self) -> "UrduVoice":
        if self._pv is not None:
            return self
        try:
            from piper import PiperVoice
        except ImportError as e:                      # pragma: no cover
            raise VoiceError(
                "piper-tts is not installed. `bash setup.sh` installs it; "
                "for a one-off: pip install piper-tts") from e
        onnx, _cfg = fetch(self.voice, self.cache)
        self._pv = PiperVoice.load(str(onnx))
        self.sr = int(self._pv.config.sample_rate)
        return self

    # -- flow -------------------------------------------------------------
    #: Silence *between* two of Piper's sentence chunks, in seconds. Piper
    #: splits internally on real sentence punctuation and the model already
    #: ends each chunk with its own tail of quiet; this is topped up so the
    #: TOTAL gap lands on the target, rather than being stacked on top of it.
    #:
    #: Why this matters, measured in the reference repo's voice study: creators
    #: pause 1.5 times a minute, line-by-line synthesis with a fixed glue
    #: silence pauses 19-23 times. The fix there was reading consecutive lines
    #: in one pass. Ours was the same defect - every sentence was its own
    #: utterance with a flat 0.30 s glued after it.
    JOIN_SENTENCE = 0.30    # after ۔ ؟ !
    JOIN_CLAUSE = 0.14      # after ، ؛ :

    def say_flow(self, text: str, length_scale: float | None = None,
                 noise_scale: float | None = None,
                 noise_w_scale: float | None = None) -> "np.ndarray":  # noqa: F821
        """Speak a whole passage in one pass, the way a person reads it.

        The engine does the sentence segmentation - it is the thing that knows
        where they are - and we only decide how much air to leave between the
        chunks it hands back.
        """
        import numpy as np
        from piper.config import SynthesisConfig

        self.load()
        if length_scale is None:
            length_scale = self.spec.get("length_scale")
        cfg = SynthesisConfig(speaker_id=self.spec.get("speaker"),
                              length_scale=length_scale,
                              noise_scale=noise_scale,
                              noise_w_scale=noise_w_scale)
        chunks = list(self._pv.synthesize(text, syn_config=cfg))
        if not chunks:
            raise VoiceError(f"voice produced no audio for {text[:40]!r}")

        parts: list[np.ndarray] = []
        for i, ch in enumerate(chunks):
            a = np.frombuffer(ch.audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            parts.append(a)
            if i < len(chunks) - 1:
                target = (self.JOIN_SENTENCE if _chunk_ends_sentence(ch)
                          else self.JOIN_CLAUSE)
                gap = target - _tail_silence(a, self.sr)
                if gap > 0:
                    parts.append(np.zeros(int(self.sr * gap), dtype=np.float32))
        return np.concatenate(parts)

    def say(self, text: str, seed: int | None = None) -> "np.ndarray":  # noqa: F821
        """One breath group -> float32 mono waveform.

        `seed` is accepted and ignored so this class is drop-in for the VITS
        engine it replaces. It is honest to ignore it: the exported ONNX graph
        is deterministic, so there is no sampling noise for a seed to control.
        The VITS model needed one because it samples; this one does not.
        """
        del seed
        import numpy as np
        self.load()
        pcm = b"".join(c.audio_int16_bytes for c in self._pv.synthesize(text))
        if not pcm:
            raise VoiceError(f"voice produced no audio for {text[:40]!r}")
        return (np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0)

    def close(self) -> None:
        """Drop the ONNX session. ffmpeg runs next and wants the memory."""
        self._pv = None

    def describe(self) -> dict:
        return {"engine": "piper", "voice": self.voice, "lang": self.lang,
                "gender": self.gender, "licence": self.licence,
                "test_only": self.test_only, "sample_rate": self.sr,
                "speaker": self.spec.get("speaker")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Urdu narration voice (Piper, CPU)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    if a.list:
        for k, spec in VOICES.items():
            mark = ""
            if k == DEFAULT_VOICE:
                mark = "  <- Urdu default"
            elif k == DEFAULT_EN_VOICE:
                mark = "  <- English default"
            warn = "  [TEST ONLY - licence not cleared]" if spec.get("test_only") else ""
            print(f"  {k:9s} {spec.get('lang','?'):3s} {spec.get('gender',''):6s} "
                  f"{spec['licence']:28s} {spec['rel']}{mark}{warn}")
        return 0

    text = a.text
    if a.text_file:
        text = Path(a.text_file).read_text(encoding="utf-8")
    if not text:
        print("nothing to say: pass --text or --text-file", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    v0 = UrduVoice(a.voice)
    if v0.lang == "ur":
        from islamic.urdu import normalize_for_speech
        text = normalize_for_speech(text)
    else:
        from islamic.english import normalize_for_speech_en
        text = normalize_for_speech_en(text)

    v = v0.load()
    import numpy as np
    import soundfile as sf
    wav = v.say(text)
    if a.out:
        sf.write(a.out, wav, v.sr)
        print(f"{a.out}  {len(wav) / v.sr:.2f}s  {v.describe()}")
    else:
        print(f"{len(wav) / v.sr:.2f}s  {v.describe()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

