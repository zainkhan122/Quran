#!/usr/bin/env python3
"""Scan an audio folder for generated naats and write the Pages manifest.

    python tools/build_manifest.py site/audio site/audio/manifest.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def build(audio_dir: str | Path, out_path: str | Path) -> dict:
    audio_dir = Path(audio_dir)
    items = []
    for mp3 in sorted(audio_dir.glob("*.mp3")):
        meta = {}
        side = mp3.with_suffix(".json")
        if side.exists():
            try:
                meta = json.loads(side.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        lines: list[str] = []
        ly = meta.get("lyrics")
        if ly and Path(ly).exists():
            lines = [l for l in Path(ly).read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.lstrip().startswith("#")]
        engine = meta.get("tts_engine") or "mms"
        label = {
            "mms": "Meta MMS baseline",
            "mms-ft": "fine-tuned Urdu voice",
            "gtts": "Google Translate TTS",
        }.get(engine, engine)
        rec = meta.get("recitation") or "read"
        if rec == "tarannum":
            label += f" + tarannum ({meta.get('raga')}/{meta.get('contour')})"
        else:
            label += " · read"
        style = meta.get("style") or "a-cappella"
        title = mp3.stem.replace("_", " ").replace("-", " ")
        items.append({
            "file": mp3.name,
            "title": title,
            "voice": label,
            "engine": engine,
            "seconds": meta.get("seconds"),
            "style": style,
            "bpm": meta.get("bpm"),
            "sample_rate": meta.get("sample_rate"),
            "breath_groups": meta.get("breath_groups"),
            "tts_rtf": meta.get("tts_rtf"),
            "recitation": rec,
            "raga": meta.get("raga"),
            "peak_rss_mb": meta.get("peak_rss_mb"),
            "lines": lines,
        })
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return manifest


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "output"
    dst = sys.argv[2] if len(sys.argv) > 2 else "output/manifest.json"
    m = build(src, dst)
    print(f"wrote {dst} with {m['count']} item(s)")
