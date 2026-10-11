"""
Authoritative word-level timings for Quran recitation.

api.quran.com returns, for a given reciter, the recitation file plus a
`segments` array:

    "segments": [[0, 1, 330, 930], [1, 2, 940, 3830], ...]
                 word_from, word_to, start_ms, end_ms

`word_from` is a 0-based index into the verse's `words` array (whose last entry
is the verse-number marker and carries no audio). So segment i gives the exact
window in which word i is recited, in the very file we play.

This is the publisher's own alignment data. The alternatives were both guesses:
- concatenating the per-word `wbw/*.mp3` clips fails because they are cut tight
  (their total is 21.1 s against the ayah's 28.6 s, so every inter-word pause is
  missing), and the API's own audio_url for the last word 404s;
- forced alignment would mean shipping a Whisper model and hoping.

We also fetch an Urdu-capable recitation set for the *translation* audio path is
not applicable - translation narration uses the Urdu TTS in naat.tts.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .sources import _get

API = "https://api.quran.com/api/v4"


def words_with_timings(ref: str, reciter: int = 7) -> tuple[list[dict], str]:
    """ref '30:21' -> ([{text, position, start, end}], audio_url)"""
    url = (f"{API}/verses/by_key/{ref}?words=true&word_fields=text_uthmani"
           f"&audio={reciter}&segments=true")
    d = _get(url, f"timings_{reciter}_{ref.replace(':', '_')}")
    v = d.get("verse")
    if not v:
        raise RuntimeError(f"quran.com returned no verse for {ref}")

    raw_words = v.get("words", [])
    audio = v.get("audio") or {}
    segs = audio.get("segments") or []
    audio_url = audio.get("url") or ""

    out: list[dict] = []
    for i, seg in enumerate(segs):
        if len(seg) != 4:
            continue
        wf, wt, s_ms, e_ms = seg
        idx = int(wf)
        if idx < 0 or idx >= len(raw_words):
            continue
        w = raw_words[idx]
        txt = (w.get("text_uthmani") or "").strip()
        # the final "word" is the ayah-number marker: correct text, but it is a
        # number glyph, not something that gets "recited word by word"
        if not txt or str(w.get("text", "")).startswith("{"):
            continue
        out.append({
            "text": txt,
            "position": int(w.get("position", idx + 1)),
            "start": s_ms / 1000.0,
            "end": e_ms / 1000.0,
        })
    if not out:
        raise RuntimeError(f"no word timings returned for {ref}")
    return out, audio_url


def download_recitation(audio_url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    url = audio_url if audio_url.startswith("http") else f"https://verses.quran.com/{audio_url}"
    req = urllib.request.Request(url, headers={"User-Agent": "islamic-video-studio/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())
    return dest
