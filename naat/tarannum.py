"""
Tarannum — turn flat read-speech Urdu into melodic recitation.

The problem
-----------
Every free Urdu TTS model (MMS-VITS, SpeechT5, Tacotron2, XTTS) was trained on
*read* speech — news and audiobooks. They produce correct Urdu with news-reader
prosody. Naat is not read; it is *recited*: sustained vowels (madd), a melodic
line in a raga, portamento between notes (meend), and a held note at the end of
a phrase (nyas). No prompt or seed gets that out of a read-speech model.

What this does
--------------
A source-filter transformation using the WORLD vocoder (pyworld):

    analyze:  F0 + spectral envelope + aperiodicity
    reshape:  replace F0 with a target melodic contour (raga + portamento +
              vibrato + phrase-final nyas), leave the spectral envelope ALONE
    resynth:  WORLD synthesis

Because the spectral envelope is untouched, the **formants survive** — it is the
same voice with the same vowel quality, now singing a contour. That is the whole
trick. Pitch-shifting audio would smear the formants and sound like a chipmunk;
source-filter separation does not.

Only voiced frames are touched, so consonants pass through unmodified and
intelligibility is preserved — which matters more here than anywhere else,
because these are sacred words.

Honest limits
-------------
This is *not* a trained singer. It imposes a plausible melodic contour on real
speech. It will read as chanting rather than as a news bulletin, and it stays
intelligible. It will not match a professional naat khawan, and it cannot invent
a melody that fits the poem's metre — it applies a chosen raga/contour. For true
singing you need a singing-voice-synthesis model (DiffSinger) fine-tuned on a
consenting reciter; see ASSESSMENT.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16_000          # VITS emits 16 kHz
FRAME_PERIOD = 5.0   # ms, WORLD default

# ---------------------------------------------------------------------------
# Ragas — semitone offsets from the tonic. Naat is commonly set in one of these.
# ---------------------------------------------------------------------------
RAGAS: dict[str, list[int]] = {
    "bhairavi": [0, 1, 3, 5, 7, 8, 10],   # komal re/ga/dha/ni — devotional, grave
    "kafi":     [0, 2, 3, 5, 7, 9, 10],   # the folk/ghazal colour
    "yaman":    [0, 2, 4, 6, 7, 9, 11],   # teevra ma — evening, serene
    "khammaj":  [0, 2, 4, 5, 7, 9, 10],   # bright, common in light classical
}

# Contour = scale-degree indices walked across a phrase. Patterned so each line
# has an arch and lands on the tonic (nyas) — the shape a reciter's breath makes.
CONTOURS: dict[str, list[int]] = {
    "gentle":  [0, 2, 4, 3, 2, 1, 0],
    "arch":    [0, 3, 4, 6, 5, 3, 2, 0],
    "call":    [4, 3, 2, 3, 4, 5, 4, 2, 0],
    "soz":     [6, 5, 4, 3, 2, 1, 0],       # descending, elegiac
    "chalan":  [0, 2, 3, 4, 3, 2, 3, 4, 5, 4, 3, 2, 0],
}


@dataclass
class TarannumSpec:
    raga: str = "bhairavi"
    contour: str = "arch"
    root_hz: float | None = None    # None -> placed near the speaker's own median F0
    note_seconds: float = 0.26      # nominal syllable/note length
    glide: float = 0.055            # portamento into each note
    vibrato_hz: float = 5.4
    vibrato_cents: float = 28.0
    vibrato_delay: float = 0.13
    final_hold: float = 1.7         # phrase-final note is this much longer
    meend_down: float = 0.6         # semitones to slide down at phrase end
    max_shift: float = 7.0          # never move more than this from the source pitch


# ---------------------------------------------------------------------------


def _segments(voiced: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous runs of True."""
    idx = np.flatnonzero(np.diff(np.r_[0, voiced.view(np.int8), 0]))
    return list(zip(idx[::2], idx[1::2]))


def _syllables(sp: np.ndarray, lo: int, hi: int, frame_period: float,
               note_seconds: float) -> list[tuple[int, int]]:
    """Split a voiced run into syllable-sized chunks.

    We segment on the spectral envelope's energy minima, which lands close to
    vowel onsets, then fall back to even division when the run is short.
    """
    if hi - lo <= 1:
        return [(lo, hi)]
    energy = np.log1p(sp[lo:hi].sum(axis=1))
    # smooth, then find local minima
    if len(energy) > 5:
        k = np.ones(5) / 5
        energy = np.convolve(energy, k, mode="same")
    mins = [i for i in range(1, len(energy) - 1)
            if energy[i] < energy[i - 1] and energy[i] <= energy[i + 1]]

    step = max(int(note_seconds * 1000 / frame_period), 1)
    bounds = [lo] + [lo + m for m in mins if lo + step <= lo + m <= hi - step] + [hi]
    # drop boundaries that leave a chunk shorter than half a note
    clean = [bounds[0]]
    for b in bounds[1:-1]:
        if b - clean[-1] >= step * 0.6:
            clean.append(b)
    clean.append(bounds[-1])

    # a run long enough to carry more notes than the contour produced -> split evenly
    if len(clean) == 2 and (hi - lo) > step * 2:
        n = max(int(round((hi - lo) / step)), 2)
        edges = np.linspace(lo, hi, n + 1).astype(int)
        return [(int(edges[i]), int(edges[i + 1])) for i in range(n)]
    return [(int(clean[i]), int(clean[i + 1])) for i in range(len(clean) - 1)]


def shape_line(y: np.ndarray, sr: int = SR, spec: TarannumSpec | None = None) -> np.ndarray:
    """Impose a melodic recitation contour on one breath group."""
    import pyworld as pw

    spec = spec or TarannumSpec()
    scale = RAGAS.get(spec.raga, RAGAS["bhairavi"])
    contour = CONTOURS.get(spec.contour, CONTOURS["arch"])

    x = np.ascontiguousarray(y.astype(np.float64))
    if len(x) < sr // 10:
        return y.astype(np.float32)

    f0, t = pw.dio(x, sr, frame_period=FRAME_PERIOD)
    sp = pw.cheaptrick(x, f0, t, sr)
    ap = pw.d4c(x, f0, t, sr)

    voiced = f0 > 0
    runs = _segments(voiced)
    if not runs:
        return y.astype(np.float32)

    # --- tonic: sit the melody on the speaker's own median pitch ------------
    # A melodic arc spans a whole *line*, not each breath group. Traversing the
    # contour per run made short runs sit on degree 0 twice and never move.
    src_pitch = float(np.median(f0[voiced]))
    n_scale = len(scale)

    # Flatten every syllable in the line, in order, across all voiced runs.
    syllables: list[tuple[int, int, int]] = []       # (run_index, a, b)
    for r_i, (lo, hi) in enumerate(runs):
        for a, b in _syllables(sp, lo, hi, FRAME_PERIOD, spec.note_seconds):
            if b > a:
                syllables.append((r_i, a, b))
    if not syllables:
        return y.astype(np.float32)

    def deg_to_hz(d: int) -> float:
        """Scale degree (may exceed the octave) -> Hz, relative to the tonic."""
        oct_, i = divmod(d, n_scale)
        return root * 2.0 ** ((scale[i] + 12 * oct_) / 12.0)

    # Centre the contour on the speaker's median so we do not spend the whole
    # line clipping against max_shift. root is chosen, then the tune sits on it.
    contour_semi = np.array([scale[d % n_scale] + 12 * (d // n_scale)
                             for d in contour], dtype=float)
    root = spec.root_hz or (src_pitch / 2.0 ** (contour_semi.mean() / 12.0))

    new_f0 = f0.copy()
    hold_frames: list[tuple[int, int, int]] = []     # (at_frame, n_extra, src_frame)
    glide_f = max(int(spec.glide * 1000 / FRAME_PERIOD), 1)
    vib_delay = int(spec.vibrato_delay * 1000 / FRAME_PERIOD)
    n_syl = len(syllables)
    prev_hz: float | None = None

    for i, (r_i, a, b) in enumerate(syllables):
        n = b - a
        last = i == n_syl - 1
        # walk the contour once across the line; final syllable lands on tonic
        if last:
            note = 0
        else:
            idx = int(round(i * (len(contour) - 1) / max(n_syl - 1, 1)))
            note = contour[min(idx, len(contour) - 1)]
        target = deg_to_hz(note)

        # keep inside the speaker's natural tessitura -> fewer artifacts
        shift = 12 * np.log2(target / src_pitch)
        shift = float(np.clip(shift, -spec.max_shift, spec.max_shift))
        target = src_pitch * 2.0 ** (shift / 12.0)

        curve = np.full(n, target)
        # portamento in from the previous note (meend) — also across a breath
        if prev_hz is not None and n > glide_f + 1:
            g = min(glide_f, n // 2)
            curve[:g] = np.linspace(prev_hz, target, g)
        # meend down at the end of the line
        if last and n > glide_f + 1:
            g = min(glide_f * 2, n // 3)
            curve[-g:] = np.linspace(target,
                                     target * 2 ** (-spec.meend_down / 12.0), g)
        # vibrato — only on notes long enough to be sustained
        if n > vib_delay + 4:
            dur = (n - vib_delay) * FRAME_PERIOD / 1000.0
            ph = 2 * np.pi * spec.vibrato_hz * np.arange(n - vib_delay) * FRAME_PERIOD / 1000.0
            ramp = np.clip(np.linspace(0, 1, n - vib_delay) * 4, 0, 1)
            depth = spec.vibrato_cents / 1200.0 * ramp
            curve[vib_delay:] *= 2.0 ** (depth * np.sin(ph))
        new_f0[a:b] = curve
        prev_hz = target

        # madd: hold the line-final vowel (capped, so a long line cannot balloon)
        if last:
            want = n * (spec.final_hold - 1.0)
            # a line often ends on a 1-2 frame syllable; without a floor the
            # hold rounds away and the whole nyas disappears.
            want = max(want, 0.30 * 1000 / FRAME_PERIOD)
            extra = int(min(want, 0.9 * 1000 / FRAME_PERIOD))
            if extra > 0:
                hold_frames.append((b, extra, a))

    # The reshaped contour IS the new pitch track. Previously f0 was only
    # replaced inside the madd branch, so a line that produced no hold was
    # resynthesised at its original pitch and tarannum silently did nothing.
    f0 = new_f0.copy()

    # --- madd: extend the spectral frames rather than time-stretching -------
    if hold_frames:
        sp_new, ap_new, f0_new = [], [], []
        pending = {at: (extra, src) for at, extra, src in hold_frames}
        for i in range(len(sp)):
            sp_new.append(sp[i]); ap_new.append(ap[i]); f0_new.append(f0[i])
            if i in pending:
                extra, src = pending[i]
                # interpolate outward from the held frame so it decays naturally
                for k in range(1, extra + 1):
                    a = 1.0 - k / (extra + 1.0)
                    j = min(src + k, len(sp) - 1)
                    sp_new.append(a * sp[src] + (1 - a) * sp[j])
                    ap_new.append(a * ap[src] + (1 - a) * ap[j])
                    f0_new.append(f0[src])
        sp = np.ascontiguousarray(np.stack(sp_new))
        ap = np.ascontiguousarray(np.stack(ap_new))
        f0 = np.ascontiguousarray(np.stack(f0_new))

    out = pw.synthesize(f0, sp, ap, sr)
    peak = float(np.abs(out).max()) or 1.0
    return (out / peak * 0.92).astype(np.float32)


class TarannumShaper:
    """Apply tarannum to each recitation line."""

    def __init__(self, spec: TarannumSpec | None = None):
        self.spec = spec or TarannumSpec()

    def __call__(self, y: np.ndarray, sr: int = SR) -> np.ndarray:
        return shape_line(y, sr, self.spec)
