"""
Narration-grade Urdu text preparation.

Why this file exists
--------------------
Urdu orthography writes the consonants and *omits the short vowels*. A
synthesiser handed "علم" cannot know whether it is `ilm`, `alam` or `ulam`.
This is the root cause of Urdu TTS sounding robotic, and it is not something a
better model can fix on its own: the paper *Automatic Diacritization for Urdu*
(Ali & Hussain) puts it bluntly — "it would not be possible to create a text to
speech system of Urdu using this under-specified input text".

We cannot diacritize (that needs a model we do not have on CPU), but we can do
the *other* half of the job, which is free and determinate: hand the engine
text that contains nothing it is not designed to say.

Measured on this box, the four defects below are what actually reached the
engine from our own published copy:

    "اور اسی کے نشانات (اور تصرفات) میں سے ہے کہ ..."   <- bracket aside
    "... پہنانے والے کی طرح ہے ۱؎۔"                      <- footnote marker
    "... فرض ہے، ..."                                    <- bare ASCII punctuation

Rules
-----
1. footnote markers are removed **before** digits are expanded, else "۱؎"
   becomes the spoken word "ایک" at the end of a hadith;
2. numerals become words ("پانچ سو", never "500") — the published benchmark
   found MMS fails outright on digits, and digits have no fixed reading in
   Urdu either;
3. bracketed asides become commas. They are *kept*, not deleted: the translator
   wrote them, the on-screen card shows them, and dropping them from the audio
   would make the narration disagree with the screen;
4. real Urdu punctuation (`،` `۔`) replaces ASCII `,` `.`, because the engine
   derives its pauses from those characters.

This module is pure-stdlib and has no dependency on any model, so it is cheap
to test and safe to run in a plan-time check.

Usage:
    python3 -m islamic.urdu --text-file in.txt [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Footnote / reference markers
# ---------------------------------------------------------------------------

# Arabic-Indic and Extended Arabic-Indic digits.
_DIGITS = {
    **{chr(0x06F0 + i): str(i) for i in range(10)},   # ۰۱...۹  Urdu
    **{chr(0x0660 + i): str(i) for i in range(10)},   # ٠١...٩  Arabic
}

# U+060E is the "poetic verse sign" and U+060F "sign of misra" — in printed
# Urdu they are dropped in as footnote daggers after a numeral ("۱؎").
_MARKER = "\u060e\u060f\u0610\u0611\ufd3e\ufd3f*"
_FOOTNOTE = re.compile(r"[0-9\u06f0-\u06f9\u0660-\u0669]+\s*[" + _MARKER + r"]")
_BARE_MARK = re.compile(r"[*†‡\u060e\u060f]")

# Arabic honourific / annotation characters a tokenizer cannot voice.
_EXPAND = {
    "\ufdfa": " صلی اللہ علیہ وسلم ",   # ﷺ
    "\ufdfb": " جل جلالہ ",             # ﷻ
    "\ufdfd": " بسم اللہ الرحمن الرحیم ",
    "%": " فیصد ",
    "&": " اور ",
    # ASCII punctuation that has an Urdu twin the engine actually understands
    ",": "، ", ".": "۔ ", "?": "؟ ", ";": "؛ ",
    # brackets around a translator's aside -> a spoken pause, not a deletion
    "(": "، ", ")": "، ", "[": "، ", "]": "، ", "{": "، ", "}": "، ",
}

# ---------------------------------------------------------------------------
# 2. Numbers
# ---------------------------------------------------------------------------

_UNITS = [
    "صفر", "ایک", "دو", "تین", "چار", "پانچ", "چھ", "سات", "آٹھ", "نو",
    "دس", "گیارہ", "بارہ", "تیرہ", "چودہ", "پندرہ", "سولہ", "سترہ", "اٹھارہ", "انیس",
    "بیس", "اکیس", "بائیس", "تئیس", "چوبیس", "پچیس", "چھبیس", "ستائیس", "اٹھائیس", "انتیس",
    "تیس", "اکتیس", "بتیس", "تینتیس", "چونتیس", "پینتیس", "چھتیس", "سینتیس", "اڑتیس", "انتالیس",
    "چالیس", "اکتالیس", "بیالیس", "تینتالیس", "چوالیس", "پینتالیس", "چھیالیس", "سینتالیس", "اڑتالیس", "انچاس",
    "پچاس", "اکاون", "باون", "ترپن", "چون", "پچپن", "چھپن", "ستاون", "اٹھاون", "انسٹھ",
    "ساٹھ", "اکسٹھ", "باسٹھ", "ترسٹھ", "چونسٹھ", "پینسٹھ", "چھیاسٹھ", "سڑسٹھ", "اڑسٹھ", "انہتر",
    "ستر", "اکہتر", "بہتر", "تہتر", "چوہتر", "پچہتر", "چھہتر", "ستتر", "اٹھہتر", "اناسی",
    "اسی", "اکیاسی", "بیاسی", "تراسی", "چوراسی", "پچاسی", "چھیاسی", "ستاسی", "اٹھاسی", "نواسی",
    "نوے", "اکانوے", "بانوے", "ترانوے", "چورانوے", "پچانوے", "چھیانوے", "ستانوے", "اٹھانوے", "ننانوے",
]
_HUNDRED = "سو"
_SCALES = [(10_000_000, "کروڑ"), (100_000, "لاکھ"), (1_000, "ہزار")]


def number_to_urdu(n: int) -> str:
    """0 <= n <= 99,99,99,999 -> Urdu cardinal words (South-Asian scale)."""
    if n < 0:
        return "منفی " + number_to_urdu(-n)
    if n < 100:
        return _UNITS[n]
    if n < 1000:
        h, r = divmod(n, 100)
        out = ("" if h == 1 else _UNITS[h] + " ") + _HUNDRED
        return out + (" " + _UNITS[r] if r else "")
    for scale, word in _SCALES:
        if n >= scale:
            q, r = divmod(n, scale)
            out = number_to_urdu(q) + " " + word
            return out + (" " + number_to_urdu(r) if r else "")
    raise AssertionError("unreachable")     # pragma: no cover


# ---------------------------------------------------------------------------
# 3. Normalisation
# ---------------------------------------------------------------------------

_STRIP_CATEGORIES = {"Mn", "Me", "Cf", "Co", "Cs", "So", "Sk"}
_KEEP_EXTRA = set(" \t\n،۔؟!:؛۔-—\u200c")   # includes ZWNJ (Urdu half-space)

#: Only these blocks may be spoken. This is deliberately a *whitelist of
#: scripts*, not "any letter": a lone Latin word left in the copy (a stray "k",
#: a Roman transliteration, an English gloss) is category Lo/Ll too, and an
#: eSpeak Urdu voice handed Latin will spell it out letter by letter.
_ARABIC_BLOCKS = (
    (0x0600, 0x06FF),    # Arabic (carries the Urdu letters)
    (0x0750, 0x077F),    # Arabic Supplement
    (0x08A0, 0x08FF),    # Arabic Extended-A
    (0xFB50, 0xFDFF),    # Arabic Presentation Forms-A (incl. ﷺ U+FDFA)
    (0xFE70, 0xFEFF),    # Arabic Presentation Forms-B
)


def _is_spoken_letter(ch: str) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in _ARABIC_BLOCKS)


def _fold_digits(text: str) -> str:
    return "".join(_DIGITS.get(c, c) for c in text)


def _expand_numbers(text: str) -> str:
    """ASCII digits -> Urdu words, so "500" is read as "پانچ سو"."""
    def sub(m: re.Match) -> str:
        s = m.group(0)
        if s.startswith("0") and len(s) > 1:      # keep "007" style ids alone
            return " ".join(_UNITS[int(c)] for c in s)
        try:
            return number_to_urdu(int(s))
        except (ValueError, AssertionError):
            return s
    return re.sub(r"\d+", sub, text)


def normalize_for_speech(text: str, *, expand_numbers: bool = True,
                         drop_comments: bool = True) -> str:
    """Return text that is safe and complete to *speak*, keeping line breaks.

    Line breaks are preserved because `split_breath_groups` uses them as
    utterance boundaries; anything else is collapsed.
    """
    t = text

    if drop_comments:
        t = "\n".join(ln for ln in t.splitlines()
                      if not ln.lstrip().startswith("#"))

    # 1. markers BEFORE digits
    t = _FOOTNOTE.sub(" ", t)
    t = _BARE_MARK.sub(" ", t)

    # 2. symbols a tokenizer cannot voice
    for k, v in _EXPAND.items():
        t = t.replace(k, v)

    # 3. digits
    t = _fold_digits(t)
    if expand_numbers:
        t = _expand_numbers(t)

    # 4. strip everything that is not an Urdu/Arabic letter, a space, a
    #    punctuation mark we chose, or a combining mark.
    out = []
    for ch in t:
        if ch in _KEEP_EXTRA:
            out.append(ch)
        elif _is_spoken_letter(ch):
            out.append(ch)
        elif unicodedata.category(ch) in _STRIP_CATEGORIES:
            out.append(ch)              # keeping harakat when the source has them
        else:
            out.append(" ")
    t = "".join(out)

    # 5. tighten up per line
    lines = []
    for ln in t.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        ln = re.sub(r"\s+([،؛۔؟!])", r"\1", ln)       # no space before punctuation
        ln = re.sub(r"(?:،\s*){2,}", "، ", ln)       # collapse "، ،"
        ln = ln.strip(" ،؛")
        if ln:
            lines.append(ln)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Word counting (shared with the video gate)
# ---------------------------------------------------------------------------

def words(text: str) -> list[str]:
    """Tokens that contain at least one Unicode letter.

    Uthmani text is dense with waqf marks (ۚ ۖ ۛ) and verse numbers (٢١); a
    plain `split()` counts those as words and makes the timing check off by
    one. `tools/check_video.py` uses the identical rule — keep them in step.
    """
    return [w for w in text.split()
            if any(unicodedata.category(c).startswith("L") for c in w)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prepare Urdu text for narration")
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    src = Path(a.text_file).read_text(encoding="utf-8")
    dst = normalize_for_speech(src)
    if a.out:
        Path(a.out).write_text(dst, encoding="utf-8")
    if a.json:
        print(json.dumps({"in_chars": len(src), "out_chars": len(dst),
                          "bytes_removed": len(src) - len(dst)},
                         ensure_ascii=False))
    else:
        print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
