"""
Urdu Naat TTS engine.

Model: facebook/mms-tts-urd-script_arabic  (VITS, 36.3M params, fp32)
Verified in this sandbox: 2 vCPU / 2 GB RAM / no GPU
  - load        : ~4.7 s
  - peak RSS    : ~758 MB
  - throughput  : RTF 0.23x  (3.9 s of audio in 0.9 s) -> ~4x faster than realtime

Design notes
------------
VITS checkpoints are trained on single utterances. Feeding it a whole naat
(broken into lines here) degrades quality badly, so we:
  1. normalise the Urdu text (expand honorifics, unify punctuation),
  2. split it into breath-sized lines,
  3. synthesise each line independently,
  4. stitch with natural pauses.
This also keeps peak RAM flat, no matter how long the naat is.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
# All three are free. None of them clones a specific real person's identity.
ENGINES: dict[str, str] = {
    # offline, 36 M params, measured 704 MB peak / RTF 0.23
    "mms": "facebook/mms-tts-urd-script_arabic",
    # offline, same architecture fine-tuned on a real Urdu speaker.
    # measured 951 MB peak / RTF 0.25, slower more deliberate delivery.
    "mms-ft": "syedmuhammad/mms-tts-urdu-vits_finetuned",
    # online, Google Translate's TTS endpoint via gTTS. Fast and free but
    # rate-limited and an unofficial endpoint - fallback only.
    "gtts": "gtts",
}
DEFAULT_ENGINE = "mms"
TARGET_SR = 44_100  # we resample up at mix time; VITS itself emits 16 kHz

LEXICON_PATH = Path(__file__).resolve().parent.parent / "lexicon" / "urdu_overrides.json"


def load_lexicon(path: Path | None = None) -> dict[str, str]:
    """Surface form -> spoken form overrides, applied to the text before TTS.

    This is our practical take on the PronouncUR idea: a hand-curated layer
    that guarantees devotional vocabulary is pronounced the way a reciter
    would say it, independent of what any one model learned.
    """
    p = path or LEXICON_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}



# ----------------------------------------------------------------------------
# Urdu text normalisation
# ----------------------------------------------------------------------------

# Symbols a TTS tokenizer cannot voice -> spelled out the way a reciter says them.
EXPANSIONS = {
    "\uFDFA": "صلی اللہ علیہ وسلم",   # ﷺ
    "\uFDFB": "جل جلالہ",             # ﷻ
    "\u0610": "", "\u0611": "",       # stray Arabic marks
    "\u06DD": "",
    "﷽": "بسم اللہ الرحمن الرحیم",
    "%": "فیصد", "&": "اور", "+": "اور",
}

# Characters we keep: Arabic/Urdu block, Urdu-specific letters, spaces, punctuation
_KEEP = re.compile(r"[^\u0600-\u06FF\u0750-\u077F\s،۔؟!:؛۔\-]")
# Urdu full stop / comma variants -> clean ones
_PUNCT = {"۔": "۔", ",": "،", "?": "؟", ";": "؛"}


def normalize_urdu(text: str, lexicon: dict[str, str] | None = None) -> str:
    """Make raw copy-pasted Urdu safe for a VITS tokenizer."""
    # drop authoring comments BEFORE expansion, else a '#' note containing
    # the honourific ﷺ would expand into real Urdu and get recited.
    t = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    t = t.strip()
    for k, v in EXPANSIONS.items():
        t = t.replace(k, v)
    for k, v in (lexicon or {}).items():
        t = t.replace(k, v)
    # strip roman transliteration / emoji / markdown that crept in
    t = _KEEP.sub(" ", t)
    for k, v in _PUNCT.items():
        t = t.replace(k, v)
    # collapse whitespace, but keep line structure (lines = breath groups)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


# VITS text encoder + its relative-position attention needs a few tokens;
# shorter inputs raise "narrow(): length must be non-negative".
MIN_WORDS = 2
_URDU_LETTER = re.compile(r"[\u0600-\u06FF]")


def _is_speakable(group: str) -> bool:
    """Drop stray punctuation-only fragments left by line splitting."""
    return len(_URDU_LETTER.findall(group)) >= 4


def split_breath_groups(text: str, max_chars: int = 90,
                        lexicon: dict[str, str] | None = None) -> list[str]:
    """Split naat text into groups a reciter would take in one breath."""
    groups: list[str] = []
    for line in normalize_urdu(text, lexicon).splitlines():
        # split on Urdu sentence enders first
        for part in re.split(r"(?<=۔)|(?<=؟)", line):
            part = part.strip(" ،؛")
            if not part:
                continue
            if len(part) <= max_chars:
                groups.append(part)
            else:  # very long line -> chop on commas
                buf = ""
                for chunk in part.split("،"):
                    chunk = chunk.strip()
                    if len(buf) + len(chunk) + 1 <= max_chars:
                        buf = f"{buf}، {chunk}" if buf else chunk
                    else:
                        if buf:
                            groups.append(buf)
                        buf = chunk
                if buf:
                    groups.append(buf)
    return [g for g in groups if _is_speakable(g)]


# ----------------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------------


@dataclass
class SynthesisReport:
    lines: list[str] = field(default_factory=list)
    seconds: float = 0.0
    wall_seconds: float = 0.0
    peak_rss_mb: float = 0.0

    @property
    def rtf(self) -> float:
        return self.wall_seconds / self.seconds if self.seconds else 0.0


class NaatTTS:
    """Lazy-loading Urdu recitation engine.

    engine: 'mms' | 'mms-ft' | 'gtts'   (see ENGINES)
    """

    def __init__(self, engine: str = DEFAULT_ENGINE, model_id: str | None = None,
                 threads: int = 2, lexicon_path: Path | None = None):
        self.engine = engine
        self.model_id = model_id or ENGINES.get(engine, ENGINES[DEFAULT_ENGINE])
        self.threads = threads
        self.lexicon = load_lexicon(lexicon_path)
        self._model = None
        self._tok = None
        self.sr = 16_000

    # -- offline paths ------------------------------------------------------
    def load(self):
        if self.engine == "gtts" or self._model is not None:
            return self
        import torch
        from transformers import AutoTokenizer, VitsModel

        torch.set_num_threads(self.threads)
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = VitsModel.from_pretrained(self.model_id).eval()
        self.sr = int(self._model.config.sampling_rate)
        return self

    def say(self, text: str, seed: int | None = None) -> np.ndarray:
        """One breath group -> float32 mono waveform."""
        if self.engine == "gtts":
            return self._gtts(text)
        import torch

        self.load()
        if seed is not None:
            torch.manual_seed(seed)
        ids = self._tok(text, return_tensors="pt")
        if ids["input_ids"].shape[-1] < 4:
            # VITS relative-position attention cannot handle near-empty inputs
            raise ValueError(f"breath group too short for VITS: {text!r}")
        with torch.no_grad():
            wav = self._model(**ids).waveform
        return wav.squeeze().numpy().astype(np.float32)

    # -- online fallback ----------------------------------------------------
    def _gtts(self, text: str) -> np.ndarray:
        """Google Translate TTS. Free, fast, but an unofficial endpoint."""
        from gtts import gTTS

        with tempfile.TemporaryDirectory() as d:
            mp3 = Path(d) / "t.mp3"
            wav = Path(d) / "t.wav"
            gTTS(text, lang="ur").save(str(mp3))
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
                 "-ar", str(self.sr), "-ac", "1", str(wav)],
                check=True, capture_output=True)
            data, sr = sf.read(str(wav), dtype="float32")
            self.sr = sr
        return data

    # -- full naat ----------------------------------------------------------
    def recite(
        self,
        lyrics: str,
        out_path: str | Path,
        pause_short: float = 0.35,
        pause_long: float = 0.9,
        seed: int = 1234,
        shaper=None,
    ) -> SynthesisReport:
        """Full naat: normalise -> split -> synth each breath -> stitch.

        shaper: optional callable(waveform) -> waveform applied to each line,
        used to impose a melodic recitation contour (see naat.tarannum).
        """
        import resource

        t0 = time.time()

        # gTTS paces a whole passage far better than it paces fragments, and
        # it already inserts its own sentence pauses.
        if self.engine == "gtts":
            text = normalize_urdu(lyrics, self.lexicon).replace("\n", "، ")
            full = self._gtts(text)
            peak = float(np.abs(full).max()) or 1.0
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(out_path, (full / peak * 0.92).astype(np.float32), self.sr)
            return SynthesisReport(
                lines=[text], seconds=len(full) / self.sr,
                wall_seconds=time.time() - t0,
                peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            )

        groups = split_breath_groups(lyrics, lexicon=self.lexicon)
        if not groups:
            raise ValueError("No Urdu text left after normalisation.")

        pieces: list[np.ndarray] = []
        kept: list[str] = []
        for i, g in enumerate(groups):
            # a line ending in ۔ is a complete stanza -> longer pause
            pause = pause_long if g.rstrip().endswith("۔") else pause_short
            try:
                line = self.say(g, seed=seed + i)
                if shaper is not None:
                    line = shaper(line, self.sr)
                pieces.append(line)
            except Exception as exc:  # one bad fragment must not kill the naat
                print(f"[naat.tts] skipped line {i}: {exc}")
                continue
            pieces.append(np.zeros(int(self.sr * pause), dtype=np.float32))
            kept.append(g)

        full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
        peak = float(np.abs(full).max()) or 1.0
        full = (full / peak * 0.92).astype(np.float32)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out_path, full, self.sr)

        return SynthesisReport(
            lines=kept,
            seconds=len(full) / self.sr,
            wall_seconds=time.time() - t0,
            peak_rss_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        )
