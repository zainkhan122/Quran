"""
Mix + master a naat: Urdu vocal bed + optional backing -> stereo WAV/MP3.

Uses ffmpeg (filter graph incl. sidechain ducking + EBU R128 loudness
normalisation). Falls back to a NumPy path if ffmpeg is unavailable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44_100
LUFS_TARGET = -16.0  # good for YouTube / WhatsApp / web


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{p.stderr[-1800:]}")


def _to_stereo_44k(src: Path, dst: Path) -> None:
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
          "-ar", str(SR), "-ac", "2", str(dst)])


def _numpy_fallback(vocal: Path, backing: Path | None, out_wav: Path,
                    vocal_gain: float, backing_gain: float) -> None:
    v, sr = sf.read(vocal, dtype="float32", always_2d=True)
    if sr != SR:
        raise RuntimeError("Install ffmpeg for resampling, or pre-render at 44.1 kHz.")
    bed = np.zeros_like(v)
    if backing and Path(backing).exists():
        b, sr2 = sf.read(backing, dtype="float32", always_2d=True)
        if sr2 != sr:
            raise RuntimeError("sample-rate mismatch between vocal and backing")
        m = min(len(bed), len(b))
        bed[:m] = b[:m]
    mix = v * vocal_gain + bed * backing_gain
    peak = float(np.abs(mix).max()) or 1.0
    sf.write(out_wav, (mix / peak * 0.95).astype(np.float32), sr)


def mix_naat(
    vocal_path: str | Path,
    backing_path: str | Path | None,
    out_dir: str | Path,
    stem: str = "naat",
    vocal_gain: float = 1.0,
    backing_gain: float = 0.62,
    duck: bool = True,
    lufs: float = LUFS_TARGET,
) -> dict:
    """Returns a dict describing the rendered files."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_out = out_dir / f"{stem}.wav"
    mp3_out = out_dir / f"{stem}.mp3"
    meta = {"vocal": str(vocal_path), "backing": str(backing_path) if backing_path else None}

    if not _have("ffmpeg"):
        _numpy_fallback(Path(vocal_path), backing_path, wav_out, vocal_gain, backing_gain)
        meta["engine"] = "numpy-fallback"
        meta["wav"] = str(wav_out)
        return meta

    tmp = out_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    v44 = tmp / "v44.wav"
    _to_stereo_44k(Path(vocal_path), v44)

    if backing_path and Path(backing_path).exists():
        b44 = tmp / "b44.wav"
        _to_stereo_44k(Path(backing_path), b44)
        if duck:
            # sidechain-duck the music under the recitation, then master
            fc = (
                f"[1:a]volume={backing_gain}[bed];"
                f"[bed][0:a]sidechaincompress=threshold=0.05:ratio=6:attack=25:release=420[ducked];"
                f"[0:a]volume={vocal_gain}[vox];"
                f"[vox][ducked]amix=inputs=2:duration=longest:normalize=0[mixed];"
                f"[mixed]loudnorm=I={lufs}:TP=-1.5:LRA=11[out]"
            )
            inputs = ["-i", str(v44), "-i", str(b44)]
        else:
            fc = (f"[0:a]volume={vocal_gain}[v];[1:a]volume={backing_gain}[b];"
                  f"[v][b]amix=inputs=2:duration=longest:normalize=0[mixed];"
                  f"[mixed]loudnorm=I={lufs}:TP=-1.5:LRA=11[out]")
            inputs = ["-i", str(v44), "-i", str(b44)]
    else:
        fc = f"[0:a]volume={vocal_gain}[v];[v]loudnorm=I={lufs}:TP=-1.5:LRA=11[out]"
        inputs = ["-i", str(v44)]

    _run(["ffmpeg", "-y", "-v", "error", *inputs,
          "-filter_complex", fc, "-map", "[out]", "-ar", str(SR), "-ac", "2",
          str(wav_out)])
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(wav_out),
          "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3_out)])

    info = sf.info(str(wav_out))
    meta.update(engine="ffmpeg", wav=str(wav_out), mp3=str(mp3_out),
                seconds=round(info.duration, 2), sample_rate=info.samplerate)
    shutil.rmtree(tmp, ignore_errors=True)
    return meta
