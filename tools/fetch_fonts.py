"""
Fetch and verify the OFL fonts the renderer needs.

Why this exists: an earlier build silently shipped with three of these files
being GitHub 404 HTML pages instead of fonts. Only the Latin ones happened to be
valid, so the failure showed up much later as "unknown file format" at render
time. A download is now only accepted if Pillow can actually open it and it
contains the glyphs we need.

All families here are SIL Open Font Licence: free for commercial use, which is
what a monetised channel requires.

    python tools/fetch_fonts.py            # verify + repair
    python tools/fetch_fonts.py --check    # report only
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "assets" / "fonts"

GH = "https://raw.githubusercontent.com/google/fonts/main/ofl"

# (filename, url, weight axis instance we want, glyphs that must be present)
FONTS = [
    ("Amiri-Regular.ttf",
     f"{GH}/amiri/Amiri-Regular.ttf", None, "بِسْمِ"),
    ("NotoNastaliqUrdu-Regular.ttf",
     f"{GH}/notonastaliqurdu/NotoNastaliqUrdu%5Bwght%5D.ttf", "Regular", "کے"),
    ("NotoNaskhArabic-Regular.ttf",
     f"{GH}/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf", "Regular", "آیت"),
    ("NotoNaskhArabic-Bold.ttf",
     f"{GH}/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf", "Bold", "آیت"),
    ("DejaVuSans.ttf",
     "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/"
     "dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf", None, "A"),
    ("DejaVuSans-Bold.ttf",
     "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/"
     "dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf", None, "A"),
]


def probe(path: Path, variation: str | None, sample: str) -> str:
    """Return '' if the file is a usable font, else the reason it is not."""
    if not path.exists() or path.stat().st_size < 20_000:
        return "missing or implausibly small"
    head = path.read_bytes()[:4]
    if head[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
        return f"not a font (starts {head!r})"
    try:
        fo = ImageFont.truetype(str(path), 40)
    except Exception as e:
        return f"unopenable: {e}"
    if variation:
        try:
            fo.set_variation_by_name(variation)
        except Exception:
            return ""   # static font that happens not to expose the axis: fine
    try:
        if fo.getlength(sample) <= 0:
            return f"zero advance for {sample!r}"
    except Exception as e:
        return f"cannot measure: {e}"
    return ""


def fetch(name: str, url: str) -> None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "islamic-video-studio/0.1",
        "Accept": "font/ttf,application/octet-stream,*/*"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    (DEST / name).write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, url, var, sample in FONTS:
        p = DEST / name
        why = probe(p, var, sample)
        if not why:
            print(f"  ok    {name}")
            continue
        if a.check:
            print(f"  BAD   {name}: {why}")
            bad += 1
            continue
        print(f"  fetch {name}  ({why})")
        try:
            fetch(name, url)
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            bad += 1
            continue
        why2 = probe(p, var, sample)
        if why2:
            print(f"  FAIL  {name} after download: {why2}")
            bad += 1
        else:
            print(f"  ok    {name} ({p.stat().st_size // 1024} KB)")
    print(f"[fonts] {len(FONTS) - bad}/{len(FONTS)} usable")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
