"""
Naat backing-track synthesiser - pure NumPy, no ML weights, runs anywhere.

Why this exists
---------------
Text-to-music models (MusicGen / ACE-Step / YuE) need 4-16 GB RAM.
The sandbox has 2 GB, so those can only run on GitHub Actions (free, 16 GB)
or in the browser. For everyday work inside the sandbox we synthesise the
backing directly.

Traditional naat is very often *a cappella*. Many scholars hold that
instrumental music is not permissible, so the DEFAULT mode is "none".
The percussion/drone modes are opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf

SR = 44_100

# ---------------------------------------------------------------- note maths


def hz(semitones_from_a4: float) -> float:
    return 440.0 * 2.0 ** (semitones_from_a4 / 12.0)


# D minor-ish / Bhairavi-flavoured scale (semitones from A4). Naats commonly
# sit in this devotional, slightly melancholic colour.
SCALE = [-14, -12, -10, -9, -7, -5, -3, -2, 0, 2, 3, 5]  # D E F G A Bb C D


def adsr(n: int, a=0.01, d=0.1, sustain=0.7, r=0.2) -> np.ndarray:
    """Attack / decay / sustain / release envelope of length n."""
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    ns = max(n - na - nd - nr, 1)
    env = np.concatenate([
        np.linspace(0, 1, na, endpoint=False) if na else np.empty(0),
        np.linspace(1, sustain, nd, endpoint=False) if nd else np.empty(0),
        np.full(ns, sustain),
        np.linspace(sustain, 0, nr) if nr else np.empty(0),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


# ------------------------------------------------------------- instruments


def ney(dur: float, f: float, vibrato=5.0, breath=0.03) -> np.ndarray:
    """Breathy end-blown flute: sine + odd harmonics + noise + vibrato."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.008 * np.sin(2 * np.pi * vibrato * t) * np.clip(t / 0.4, 0, 1)
    ph = 2 * np.pi * np.cumsum(f * vib) / SR
    tone = (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.10 * np.sin(3 * ph)
            + 0.05 * np.sin(4 * ph))
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, n)
    # gentle one-pole low-pass on the breath noise
    for _ in range(2):
        noise = np.convolve(noise, [0.25, 0.5, 0.25], mode="same")
    env = adsr(n, a=0.08, d=0.15, r=0.25)
    return ((tone + breath * noise * 12) * env * 0.22).astype(np.float64)


def drone(dur: float, root: float, partials=(1, 2, 3, 4, 5)) -> np.ndarray:
    """Harmonium / tanpura-style sustained chord pad."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, p in enumerate(partials):
        det = 1 + 0.0015 * np.sin(2 * np.pi * (0.13 + 0.07 * i) * t)
        out += (1.0 / (i + 1.6)) * np.sin(2 * np.pi * root * p * t * det)
    swell = np.clip(t / 1.5, 0, 1) * np.clip((dur - t) / 1.5, 0, 1)
    return out * swell * 0.14


def dum(dur=0.34, f0=78.0) -> np.ndarray:
    """Daf / tabla bass stroke: fast pitch-dropping sine + attack noise."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (1 + 1.6 * np.exp(-t * 22))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    rng = np.random.default_rng(3)
    click = rng.normal(0, 1, n) * np.exp(-t * 90) * 0.35
    return (body + click) * 0.55


def tak(dur=0.16, f0=420.0) -> np.ndarray:
    """Rim / treble stroke."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * 26)
    rng = np.random.default_rng(4)
    noise = rng.normal(0, 1, n) * np.exp(-t * 55)
    for _ in range(3):
        noise = np.convolve(noise, [0.25, 0.5, 0.25], mode="same")
    return (body * 0.5 + noise * 0.5) * 0.30


# ------------------------------------------------------------------ layout

@dataclass
class BackingSpec:
    bpm: int = 66
    root: float = hz(-14)          # D3
    style: str = "daf"             # none | daf | daf-drone | drone
    intro: float = 3.0
    outro: float = 4.0


def build_backing(total_seconds: float, spec: BackingSpec | None = None) -> np.ndarray:
    """Render a backing bed of `total_seconds`, stereo float64."""
    spec = spec or BackingSpec()
    if spec.style == "none":
        return np.zeros((int(total_seconds * SR), 2))

    n = int(total_seconds * SR)
    out = np.zeros(n)

    if "drone" in spec.style or spec.style == "drone":
        # root + fifth + octave, harmonium style
        pad = (drone(total_seconds, spec.root, (1, 1.5, 2, 3, 4))
               + 0.8 * drone(total_seconds, spec.root * (2 ** (-10 / 12)), (1, 2, 3)))
        out += pad

    if spec.style in ("daf", "daf-drone"):
        beat = 60.0 / spec.bpm
        pattern = [("dum", 0.0), ("tak", 0.5), ("tak", 0.75),
                   ("dum", 1.0), ("tak", 1.5), ("dum", 1.75), ("tak", 2.0),
                   ("tak", 2.5), ("dum", 3.0), ("tak", 3.25), ("tak", 3.5)]
        bar = 4 * beat
        pos = spec.intro
        while pos < total_seconds - spec.outro:
            for kind, offset in pattern:
                at = pos + offset * beat
                if at >= total_seconds - 0.2:
                    break
                hit = dum() if kind == "dum" else tak()
                i = int(at * SR)
                j = min(i + len(hit), n)
                out[i:j] += hit[: j - i] * 0.5
            pos += bar

    # intro / outro fades on the percussion+drone bed
    fi, fo = int(spec.intro * SR) if spec.intro else 0, int(spec.outro * SR)
    if fi:
        out[:fi] *= np.linspace(0, 1, fi)
    if fo and fo < n:
        out[-fo:] *= np.linspace(1, 0, fo)

    peak = float(np.abs(out).max()) or 1.0
    out = out / peak * 0.75

    # width: tiny decorrelation so it is not a mono blob
    rng = np.random.default_rng(11)
    d = int(0.011 * SR)
    left = out
    right = np.concatenate([np.zeros(d), out[:-d]]) * 0.96
    return np.stack([left + rng.normal(0, 1e-4, n), right], axis=1)


def write_backing(path: str, total_seconds: float, spec: BackingSpec | None = None) -> None:
    sf.write(path, build_backing(total_seconds, spec).astype(np.float32), SR)
