#!/usr/bin/env python3
"""
Measure how a narration *delivers*, not just what it says.

The agent cannot hear a wav, so it listens by measurement. The definitions here
are taken from the reference repo's voice study so the numbers are comparable
with theirs, which is the only reason they mean anything:

    metric                     creators (median)   our line-by-line   approved
    pauses per minute >=150 ms            1.5               19.2       7.5
    pitch range (semitones)              13.4               11.0      14.4
    words per minute                    184.5              187.0       205

The headline finding there was that **creators speak in continuous flow while
line-by-line synthesis manufactures pauses** - and line-by-line synthesis with a
fixed glue silence is exactly what this project was doing.

    python3 tools/voice_metrics.py FILE.wav [FILE2.wav ...]
    python3 tools/voice_metrics.py clip.mp4 --text body.txt --json

Exit status is always 0: this is an instrument, not a gate.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

# --- pause definition, matched to the reference study -----------------------
PAUSE_MS = 150.0            # a gap shorter than this is co-articulation, not a pause
SILENCE_DB = -40.0          # relative to the file's own peak; below this is quiet
FRAME_MS = 20.0

# --- pitch tracking ---------------------------------------------------------
F0_MIN, F0_MAX = 60.0, 400.0
F0_FRAME_MS, F0_HOP_MS = 40.0, 10.0
VOICING_THRESHOLD = 0.30    # autocorrelation peak / zero-lag


def load_audio(path: Path, sr: int = 22_050) -> tuple[np.ndarray, int]:
    """Any audio or video file -> mono float32, via ffmpeg (no decoder deps)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32), sr


# ---------------------------------------------------------------------------
def _frame_rms(x: np.ndarray, sr: int, frame_ms: float) -> tuple[np.ndarray, np.ndarray]:
    n = max(int(sr * frame_ms / 1000), 1)
    hops = max(len(x) // n, 1)
    trimmed = x[: hops * n].reshape(hops, n)
    rms = np.sqrt((trimmed.astype(np.float64) ** 2).mean(axis=1))
    times = (np.arange(hops) * n + n / 2) / sr
    return rms, times


def pauses(x: np.ndarray, sr: int) -> dict:
    """Silence runs >= PAUSE_MS, measured against the file's own peak.

    Trimmed of leading and trailing silence first: a file that starts with
    300 ms of nothing has not paused, it has just started.
    """
    rms, times = _frame_rms(x, sr, FRAME_MS)
    if not len(rms):
        return {"count": 0, "per_minute": 0.0, "mean_s": 0.0, "total_s": 0.0,
                "longest_s": 0.0, "speech_s": 0.0, "silence_pct": 0.0}
    peak = float(rms.max()) or 1.0
    floor = peak * 10 ** (SILENCE_DB / 20)
    quiet = rms < floor

    # trim edges
    idx = np.flatnonzero(~quiet)
    if not len(idx):
        return {"count": 0, "per_minute": 0.0, "mean_s": 0.0, "total_s": 0.0,
                "longest_s": 0.0, "speech_s": 0.0, "silence_pct": 0.0}
    quiet = quiet[idx[0]: idx[-1] + 1]
    span_s = len(quiet) * FRAME_MS / 1000

    runs: list[float] = []
    run = 0
    for q in quiet:
        if q:
            run += 1
        elif run:
            runs.append(run * FRAME_MS / 1000)
            run = 0
    if run:
        runs.append(run * FRAME_MS / 1000)

    real = [r for r in runs if r * 1000 >= PAUSE_MS]
    total = sum(real)
    return {
        "count": len(real),
        "per_minute": round(len(real) / span_s * 60, 1) if span_s else 0.0,
        "mean_s": round(total / len(real), 3) if real else 0.0,
        "total_s": round(total, 2),
        "longest_s": round(max(real), 2) if real else 0.0,
        "speech_s": round(span_s - total, 2),
        "silence_pct": round(total / span_s * 100, 1) if span_s else 0.0,
    }


# ---------------------------------------------------------------------------
def track_f0(x: np.ndarray, sr: int) -> np.ndarray:
    """Autocorrelation F0 per frame. Good enough for clean single-speaker audio.

    Music beds fool this, which is why the reference study separates vocals
    first. We measure our own narration, which has no bed, so we do not.
    """
    from scipy.signal import butter, lfilter

    lo, hi = 50.0, 500.0
    b, a = butter(4, [lo / (sr / 2), hi / (sr / 2)], btype="band")
    y = lfilter(b, a, x.astype(np.float64))

    n = int(sr * F0_FRAME_MS / 1000)
    hop = int(sr * F0_HOP_MS / 1000)
    lo_lag = int(sr / F0_MAX)
    hi_lag = int(sr / F0_MIN)
    out = []
    for start in range(0, max(len(y) - n, 1), hop):
        fr = y[start:start + n]
        if len(fr) < n:
            break
        if np.sqrt((fr ** 2).mean()) < 1e-4:
            out.append(0.0)
            continue
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, mode="full")[n - 1:]
        r0 = ac[0]
        if r0 <= 0:
            out.append(0.0)
            continue
        seg = ac[lo_lag:hi_lag]
        if not len(seg):
            out.append(0.0)
            continue
        k = int(np.argmax(seg)) + lo_lag
        if ac[k] / r0 < VOICING_THRESHOLD:
            out.append(0.0)
            continue
        # parabolic refinement around the peak
        if 0 < k < len(ac) - 1:
            y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
            denom = (y0 - 2 * y1 + y2)
            shift = 0.5 * (y0 - y2) / denom if denom else 0.0
            if abs(shift) < 1:
                k = k + shift
        out.append(sr / k if k > 0 else 0.0)
    return np.asarray([f for f in out if f > 0])


def melody(f0: np.ndarray) -> dict:
    if len(f0) < 10:
        return {"range_st": 0.0, "sd_st": 0.0, "median_hz": 0.0, "voiced_frames": len(f0)}
    st = 12 * np.log2(f0 / np.median(f0))
    return {
        "range_st": round(float(np.percentile(st, 95) - np.percentile(st, 5)), 1),
        "sd_st": round(float(st.std()), 1),
        "median_hz": round(float(np.median(f0)), 1),
        "voiced_frames": len(f0),
    }


def loudness(x: np.ndarray, sr: int) -> dict:
    rms, _ = _frame_rms(x, sr, 50.0)
    rms = rms[rms > 0]
    if not len(rms):
        return {"range_db": 0.0}
    db = 20 * np.log10(rms / rms.max() + 1e-12)
    db = db[db > -60]
    return {"range_db": round(float(np.percentile(db, 95) - np.percentile(db, 5)), 1)}


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def words_per_minute(seconds: float, text: str | None) -> float | None:
    if not text or seconds <= 0:
        return None
    n = len(_WORD.findall(text))
    return round(n / seconds * 60, 1)


def analyse(path: Path, text: str | None = None) -> dict:
    x, sr = load_audio(path)
    dur = len(x) / sr
    p = pauses(x, sr)
    m = melody(track_f0(x, sr))
    return {
        "file": str(path),
        "seconds": round(dur, 2),
        "pauses": p,
        "melody": m,
        "loudness": loudness(x, sr),
        "wpm": words_per_minute(dur, text),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Narration delivery metrics")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--text", help="narration text, for words-per-minute")
    ap.add_argument("--text-file")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    text = a.text
    if a.text_file and not text:
        text = Path(a.text_file).read_text(encoding="utf-8")
    if text and len(a.files) > 1:
        text = None                         # only meaningful for a single file

    rows = [analyse(Path(f), text) for f in a.files]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"{'file':34s} {'len':>6s} {'pause/min':>9s} {'mean':>6s} {'long':>6s} "
          f"{'sil%':>5s} {'range_st':>8s} {'loud_dB':>7s} {'wpm':>6s}")
    for r in rows:
        p, m, l = r["pauses"], r["melody"], r["loudness"]
        print(f"{Path(r['file']).name[:34]:34s} {r['seconds']:6.1f} "
              f"{p['per_minute']:9.1f} {p['mean_s']:6.2f} {p['longest_s']:6.2f} "
              f"{p['silence_pct']:5.1f} {m['range_st']:8.1f} {l['range_db']:7.1f} "
              f"{(r['wpm'] if r['wpm'] is not None else float('nan')):6.1f}")
    print("\nreference points (from the study): creators 1.5 pauses/min, "
          "line-by-line 19.2, approved sample 7.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
