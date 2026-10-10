"""
MusicGen backing tracks - the GitHub Actions path.

MusicGen-small is a 0.6B-param model (~2.4 GB of fp32 weights). Measured in
this sandbox (2 vCPU / 2 GB): it does NOT fit - the safetensors mmap fails.
On a *public* GitHub Actions runner (4 vCPU / 16 GB RAM, free) it fits
comfortably on CPU.

Locally (sandbox) the q8-ONNX build can produce ~2 s clips only; see
web/ or tools/musicgen_onnx.mjs for that path.

Prompts: MusicGen has no concept of "naat". Describe *sound*, never the
Prophet's name or any text you intend to be sung - the model will not sing
Urdu, and generating sung devotional text of any kind is out of scope here.
This module only ever produces an instrumental bed.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_ID = "facebook/musicgen-small"  # swap to musicgen-medium on a 16 GB runner

# Instrumental-only descriptors. Keep it acoustic and restrained.
STYLES = {
    "a-cappella": None,
    "ney": ("solo ney reed flute, slow meditative melody, wide reverb, no percussion, "
            "no vocals, devotional, sparse"),
    "ney-daf": ("gentle ney flute with soft frame drum daf and warm harmonium drone, "
                "devotional, slow 66 bpm, no vocals, instrumental"),
    "strings": ("warm bowed strings and harmonium pad, solemn and reverent, slow, "
                "no percussion, no vocals, instrumental"),
    "drone": ("tanpura drone with faint harmonium, still and calm, no melody, "
              "no vocals, instrumental, meditative"),
}


def _crossfade(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    if n <= 0 or len(a) < n or len(b) < n:
        return np.concatenate([a, b])
    f = np.linspace(0, 1, n)
    return np.concatenate([a[:-n], a[-n:] * (1 - f) + b[:n] * f, b[n:]])


def generate_backing(
    out_path: str | Path,
    target_seconds: float,
    style: str = "ney-daf",
    model_id: str = MODEL_ID,
    chunk_seconds: float = 15.0,
    seed: int = 4242,
) -> Path | None:
    """Render `target_seconds` of instrumental bed, looping seeded chunks."""
    prompt = STYLES.get(style)
    if prompt is None:
        return None

    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    torch.set_num_threads(4)
    t0 = time.time()
    proc = AutoProcessor.from_pretrained(model_id)
    model = MusicgenForConditionalGeneration.from_pretrained(model_id).eval()
    sr = int(model.config.audio_encoder.sampling_rate)
    print(f"[musicgen] loaded {model_id} in {time.time()-t0:.0f}s")

    # MusicGen emits 50 frames (tokens) per second of audio
    tokens = min(int(chunk_seconds * 50), 1500)
    chunks: list[np.ndarray] = []
    have = 0.0
    i = 0
    while have < target_seconds + chunk_seconds:
        torch.manual_seed(seed + i)
        ins = proc(text=[prompt], return_tensors="pt")
        with torch.no_grad():
            audio = model.generate(**ins, do_sample=True, guidance_scale=3.0,
                                   max_new_tokens=tokens)
        c = audio.squeeze().float().numpy()
        t = time.time()
        chunks.append(c)
        have += len(c) / sr
        print(f"[musicgen] chunk {i}: {len(c)/sr:.1f}s audio "
              f"(cumulative {have:.0f}s / target {target_seconds:.0f}s)")
        i += 1
        if i > 40:  # safety valve
            break

    bed = chunks[0]
    for c in chunks[1:]:
        bed = _crossfade(bed, c, int(0.9 * sr))
    bed = bed[: int(target_seconds * sr)]

    peak = float(np.abs(bed).max()) or 1.0
    bed = (bed / peak * 0.85).astype(np.float32)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, bed, sr)
    print(f"[musicgen] wrote {out_path} ({len(bed)/sr:.1f}s)")
    return out_path
