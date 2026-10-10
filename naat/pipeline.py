"""
Naat Studio pipeline - lyrics in, mastered naat out.

  python -m naat.pipeline --lyrics lyrics/sample_naat.txt --style daf-drone
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .backing import BackingSpec, build_backing, write_backing
from .mix import mix_naat
from .tts import NaatTTS

ROOT = Path(__file__).resolve().parent.parent
BPM_DEFAULT = 66


def pick_root(text: str) -> float:
    """Cheap mood heuristic: longer lines -> lower, calmer recitation key."""
    from .backing import hz
    lines = [l for l in text.splitlines() if l.strip()]
    avg = sum(len(l) for l in lines) / max(len(lines), 1)
    return hz(-16) if avg > 55 else hz(-14)


PROCEDURAL_STYLES = {"daf", "daf-drone", "drone", "full"}
MUSICGEN_STYLES = {"ney", "ney-daf", "strings"}


def _maybe_musicgen(style: str, seconds: float, out_path: Path, seed: int) -> Path | None:
    """Try the ML backing engine; degrade gracefully when RAM is short."""
    try:
        import psutil  # optional
        avail_gb = psutil.virtual_memory().available / 1e9
    except Exception:
        avail_gb = None
    if avail_gb is not None and avail_gb < 5.0:
        print(f"[pipeline] only {avail_gb:.1f} GB RAM free - MusicGen needs ~4 GB+. "
              f"Falling back to procedural backing.")
        return None
    from .musicgen import generate_backing
    return generate_backing(out_path, seconds, style=style, seed=seed)


def run(
    lyrics_path: str | Path,
    out_dir: str | Path = "output",
    style: str = "a-cappella",
    bpm: int = BPM_DEFAULT,
    stem: str | None = None,
    seed: int = 1234,
    keep_stems: bool = True,
    backing_file: str | Path | None = None,
    engine: str = "mms",
    recitation: str = "read",
    raga: str = "bhairavi",
    contour: str = "arch",
) -> dict:
    lyrics_path = Path(lyrics_path)
    raw = lyrics_path.read_text(encoding="utf-8")
    stem = stem or re.sub(r"[^a-z0-9]+", "-", lyrics_path.stem.lower()).strip("-")
    out_dir = Path(out_dir)
    stems_dir = out_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    # 1) URDU VOCAL ---------------------------------------------------------
    tts = NaatTTS(engine=engine)

    # Read speech -> melodic tarannum. See naat/tarannum.py for why this is a
    # source-filter transform and not a prompt.
    shaper = None
    if recitation == "tarannum":
        from .tarannum import TarannumShaper, TarannumSpec
        shaper = TarannumShaper(TarannumSpec(raga=raga, contour=contour))

    vocal = stems_dir / f"{stem}_vocal.wav"
    rep = tts.recite(raw, vocal, seed=seed, shaper=shaper)

    # 2) BACKING ------------------------------------------------------------
    backing = None
    if backing_file:                                   # bring your own bed
        backing = Path(backing_file)
    elif style in PROCEDURAL_STYLES:                   # NumPy synth, 2 GB-safe
        spec = BackingSpec(bpm=bpm, root=pick_root(raw),
                           style="daf-drone" if style == "full" else style,
                           intro=3.0, outro=min(6.0, rep.seconds * 0.12))
        backing = stems_dir / f"{stem}_backing.wav"
        write_backing(str(backing), rep.seconds, spec)
    elif style in MUSICGEN_STYLES:                     # needs ~4 GB+ (CI runner)
        backing = _maybe_musicgen(style, rep.seconds,
                                  stems_dir / f"{stem}_backing.wav", seed)
        if backing is None:                            # graceful degradation
            spec = BackingSpec(bpm=bpm, root=pick_root(raw), style="daf-drone",
                               intro=3.0, outro=min(6.0, rep.seconds * 0.12))
            backing = stems_dir / f"{stem}_backing.wav"
            write_backing(str(backing), rep.seconds, spec)
            style = "daf-drone (fallback)"

    # 3) MIX + MASTER -------------------------------------------------------
    meta = mix_naat(vocal, backing, out_dir, stem=stem)
    meta.update(
        lyrics=str(lyrics_path),
        style=style,
        bpm=bpm,
        breath_groups=len(rep.lines),
        vocal_seconds=round(rep.seconds, 2),
        tts_wall_seconds=round(rep.wall_seconds, 2),
        tts_rtf=round(rep.rtf, 3),
        tts_engine=engine,
        recitation=recitation,
        raga=raga if recitation == "tarannum" else None,
        contour=contour if recitation == "tarannum" else None,
        tts_model=tts.model_id,
        peak_rss_mb=round(rep.peak_rss_mb),
    )
    if not keep_stems:
        for f in stems_dir.glob(f"{stem}_*.wav"):
            f.unlink()

    (out_dir / f"{stem}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate an Urdu naat end-to-end.")
    ap.add_argument("--lyrics", required=True)
    ap.add_argument("--out", default="output")
    ap.add_argument("--style", default="a-cappella",
                    choices=["a-cappella", "none", "daf", "daf-drone", "drone",
                             "full", "ney", "ney-daf", "strings"])
    ap.add_argument("--bpm", type=int, default=BPM_DEFAULT)
    ap.add_argument("--stem")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--backing-file", help="use an existing backing track")
    ap.add_argument("--recitation", default="read", choices=["read", "tarannum"],
                    help="read=plain TTS prosody | tarannum=melodic recitation contour")
    ap.add_argument("--raga", default="bhairavi",
                    choices=["bhairavi", "kafi", "yaman", "khammaj"])
    ap.add_argument("--contour", default="arch",
                    choices=["gentle", "arch", "call", "soz", "chalan"])
    ap.add_argument("--engine", default="mms", choices=["mms", "mms-ft", "gtts"],
                    help="mms=Meta baseline (704 MB) | mms-ft=fine-tuned "
                         "(951 MB, slower delivery) | gtts=online fallback")
    a = ap.parse_args(argv)

    meta = run(a.lyrics, a.out, a.style, a.bpm, a.stem, a.seed,
               backing_file=a.backing_file, engine=a.engine,
               recitation=a.recitation, raga=a.raga, contour=a.contour)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"\nOK -> {meta.get('mp3') or meta.get('wav')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
