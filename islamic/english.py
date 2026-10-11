"""
English narration text preparation.

Deliberately much smaller than `islamic/urdu.py`, and the difference is the
point. Urdu needs a heavy normaliser because its script is under-specified and
our copy arrives with footnote daggers and bracketed asides in it. English does
not: eSpeak's English reads digits, decimals and abbreviations correctly on its
own, so "500" is "five hundred" without help, and expanding it by hand would
only remove the engine's own judgement.

What is left is genuinely ours to fix:

* **Footnote markers.** The hadith editions annotate with things like `(1)` or
  `[2]` and those get read out loud. Same defect as the Urdu `۱؎`, different
  codepoint.
* **Smart punctuation.** Copy-pasted translations carry curly quotes and en/em
  dashes. A dash is a pause and a curly quote is not a syllable.
* **Whitespace.** Non-breaking spaces and stray tabs confuse sentence
  segmentation, and it is sentence segmentation that decides where Piper
  breathes.

Usage:
    python3 -m islamic.english --text-file body.txt
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

#: A digit in brackets/parens, or a bare bracketed footnote. Stripped before
#: anything else so "[2]" cannot become "two".
_FOOTNOTE = re.compile(r"[\[(]\s*(?:note\s*)?\d{1,3}\s*[\])]", re.IGNORECASE)
#: A lone digit-right-after-a-word, which is how the printed editions mark a
#: footnote when the bracket was lost in transcription: "mercy.2 Indeed..."
_LONE_MARK = re.compile(r"(?<=[a-z.,;:)\]])\d{1,2}(?=\s|$)")

#: Characters that carry no sound but do carry meaning for the pauser.
_REPLACE = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": ", ", "\u2014": ", ", "\u2026": "...",
    "\u00a0": " ", "\u2009": " ", "\u200b": "",
    "\u200c": "", "\u200d": "",
}


def normalize_for_speech_en(text: str, *, drop_comments: bool = True) -> str:
    """Return English text that is safe to speak, keeping line structure."""
    t = text
    if drop_comments:
        t = "\n".join(ln for ln in t.splitlines() if not ln.lstrip().startswith("#"))

    t = _FOOTNOTE.sub(" ", t)
    t = _LONE_MARK.sub(" ", t)
    for k, v in _REPLACE.items():
        t = t.replace(k, v)

    lines = []
    for ln in t.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        ln = re.sub(r"\s+([,.;:!?])", r"\1", ln)
        ln = re.sub(r"\.{4,}", "...", ln)
        if ln:
            lines.append(ln)
    return "\n".join(lines)


def words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if re.search(r"[A-Za-z]", w)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prepare English text for narration")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    src = Path(a.text_file).read_text(encoding="utf-8")
    dst = normalize_for_speech_en(src)
    if a.out:
        Path(a.out).write_text(dst, encoding="utf-8")
    print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
