"""
Islamic Video Studio - professional renderer.

Design system
-------------
  canvas    1080x1920 @ 30 fps (also 1920x1080 for landscape)
  palette   deep teal-green ground, gold ornament, warm ivory text
  ornament  generated Islamic 2D art (girih lattice + islimi medallion),
            composited at low opacity BEHIND the text - geometric only,
            never figurative, as the tradition requires
  type      Amiri (Quran) · Noto Nastaliq Urdu (Urdu) · DejaVu (Latin UI)
  topic     bold, explanatory, engineered to fit ONE OR TWO lines - never one
            word, never a paragraph
  Quran     word-by-word reveal lit exactly to the recitation's own timings

Why this is fast enough for 2 CPU cores
---------------------------------------
The background AND every static layer are composited once into a "base" image
per phase. Each frame then only repaints the few words whose highlight changed
on top of a copy of that base. Rendering a 49 s video takes tens of seconds
instead of minutes, and frames stream straight into ffmpeg's stdin so no
intermediate PNGs ever touch the disk.

Word timings are authoritative, not estimated
---------------------------------------------
api.quran.com returns `audio.segments` as [word_from, word_to, start_ms, end_ms]
for the very recitation file we play. Slicing audio by correlation, or running a
forced aligner, would both be guesses; this is the publisher's own timing data.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
TEX = ROOT / "assets" / "textures"

ARABIC = FONTS / "Amiri-Regular.ttf"
URDU = FONTS / "NotoNastaliqUrdu-Regular.ttf"
UI = FONTS / "NotoNaskhArabic-Regular.ttf"
LATIN = FONTS / "DejaVuSans.ttf"
LATIN_B = FONTS / "DejaVuSans-Bold.ttf"

RTL = {"direction": "rtl", "language": "ar"}

# --------------------------------------------------------------------------
# palette
# --------------------------------------------------------------------------
GOLD = (232, 196, 126)
GOLD_HI = (255, 238, 196)
GOLD_DIM = (150, 122, 72)
IVORY = (243, 248, 245)
MUTED = (176, 200, 192)
AR_DIM = (146, 124, 84)      # not-yet-recited words: warm brass in shadow.
                              # A cold steel tone read as a rendering fault next to
                              # the gold, and pulled the eye away from the live word.
AR_DONE = (206, 178, 116)
BG_TOP = (8, 22, 19)
BG_BOT = (14, 42, 35)


@dataclass
class Comp:
    """Everything the renderer needs. Built by build_composition()."""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    topic_en: str = ""
    topic_ur: str = ""
    sub_en: str = ""                 # one-line explanatory subtitle (optional)
    reference_en: str = ""
    reference_ar: str = ""
    grade: str = ""
    arabic_words: list[dict] = field(default_factory=list)   # {text,start,end}
    body_arabic: str = ""            # static Arabic, used when no timings exist
    urdu: str = ""
    english: str = ""
    phase1: float = 0.0              # seconds, arabic word-by-word
    phase2: float = 0.0              # seconds, urdu translation
    lead: float = 0.8
    tail: float = 1.4
    crossfade: float = 0.45
    textures: bool = True
    topic_key: str = ""              # selects assets/motifs/<key>.png when present

    @property
    def total(self) -> float:
        return self.phase1 + self.phase2


# --------------------------------------------------------------------------
# background / ornament
# --------------------------------------------------------------------------

def _gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = (y / max(h - 1, 1)) ** 0.85
        d.line([(0, y), (w, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))
    return img


def _tile(img: Image.Image, tex: Image.Image, opacity: float) -> None:
    """Tile a texture across the canvas at low opacity (screen-ish blend)."""
    if tex is None:
        return
    tw, th = tex.size
    layer = Image.new("RGB", img.size, (0, 0, 0))
    for y in range(0, img.size[1], th):
        for x in range(0, img.size[0], tw):
            layer.paste(tex, (x, y))
    img.paste(Image.blend(img, Image.blend(img, layer, 0.55), opacity))


def _ink_layer(img: Image.Image, path: Path, opacity: float = 0.55,
               scale: float = 0.98, cy: float = 0.46,
               colour: tuple = GOLD) -> None:
    """Composite artwork as pure gold linework, not as a pasted rectangle.

    The motif images are gold strokes on their own dark ground. Blending them in
    as opaque images would leave a visible rectangular seam where their
    background meets ours, so the drawing is converted to a mask - everything
    brighter than its own background becomes ink - and re-coloured to the
    palette. The result is that only the lines land on the frame.
    """
    if not path.exists():
        return
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return
    w, h = img.size
    nw = int(w * scale)
    nh = max(int(im.size[1] * nw / im.size[0]), 1)
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (w - nw) // 2, int(h * cy - nh / 2)

    lum = im.convert("L")
    px = list(lum.getdata())
    # the flat ground is whatever dominates the image; anything above it is ink
    ground = sorted(px)[int(len(px) * 0.72)]
    lo, hi = ground + 12, max(ground + 60, 245)
    mask = lum.point(lambda v: 0 if v <= lo else min(255, int((v - lo) * 255 / (hi - lo))))
    mask = mask.point(lambda v: int(v * opacity))
    ink = Image.new("RGBA", (nw, nh), (*colour, 0))
    ink.putalpha(mask)
    base = img.crop((x, y, x + nw, y + nh)).convert("RGBA")
    img.paste(Image.alpha_composite(base, ink).convert("RGB"), (x, y))


def motif_for(topic_key: str) -> Path | None:
    """Topic-specific 2D art, if one has been drawn for that topic."""
    if not topic_key:
        return None
    for ext in (".png", ".jpg"):
        p = ROOT / "assets" / "motifs" / f"{topic_key}{ext}"
        if p.exists():
            return p
    return None


def _medallion(img: Image.Image, tex: Image.Image, opacity: float,
               scale: float = 0.86, cy: float = 0.46) -> None:
    if tex is None:
        return
    w, h = img.size
    nw = int(w * scale)
    nh = int(tex.size[1] * nw / tex.size[0])
    t = tex.resize((nw, nh), Image.LANCZOS)
    x, y = (w - nw) // 2, int(h * cy - nh / 2)
    base = img.crop((x, y, x + nw, y + nh))
    img.paste(Image.blend(base, Image.blend(base, t, 0.5), opacity), (x, y))


def _vignette(img: Image.Image, strength: float = 0.55) -> None:
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    dm = ImageDraw.Draw(m)
    pad = int(min(w, h) * 0.06)
    dm.ellipse([-pad * 2, -pad, w + pad * 2, h + pad], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.16)))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    img.paste(Image.composite(img, dark, m), (0, 0))


def _frame_border(img: Image.Image, inset: int = 30) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    d.rectangle([inset, inset, w - inset, h - inset], outline=(*GOLD, 70), width=2)
    d.rectangle([inset + 9, inset + 9, w - inset - 9, h - inset - 9],
                outline=(*GOLD, 26), width=1)
    # corner ticks
    L = 46
    for cx, cy, dx, dy in ((inset, inset, 1, 1), (w - inset, inset, -1, 1),
                           (inset, h - inset, 1, -1), (w - inset, h - inset, -1, -1)):
        d.line([(cx, cy), (cx + dx * L, cy)], fill=(*GOLD, 120), width=3)
        d.line([(cx, cy), (cx, cy + dy * L)], fill=(*GOLD, 120), width=3)


def _body_scrim(img: Image.Image, top: int, bottom: int, pad: int) -> None:
    """A soft dark bed behind the body text.

    Ornament behind the words is what the brief asked for; ornament competing
    with the words is a legibility bug. A heavily blurred black shape pushes the
    artwork back exactly where type sits, and leaves it visible everywhere else.
    """
    w, h = img.size
    m = Image.new("L", (w, h), 0)
    # 88 -> 132. The brief asked for the art to sit behind the words and be
    # readable through them, not merely present: at 88 the topical motif still
    # competed with the Arabic on a busy frame.
    ImageDraw.Draw(m).rounded_rectangle(
        [pad - 20, top - 40, w - pad + 20, bottom + 40], radius=90, fill=132)
    m = m.filter(ImageFilter.GaussianBlur(int(w * 0.055)))
    dark = Image.new("RGBA", (w, h), (2, 10, 8, 255))
    dark.putalpha(m)
    img.paste(Image.alpha_composite(img.convert("RGBA"), dark).convert("RGB"), (0, 0))


def background(w: int, h: int, use_textures: bool = True,
               topic_key: str = "") -> Image.Image:
    """Ground + ornament.

    The topical motif is the layer the user actually asked for: art that says
    something about *this* subject, set far enough back that it never competes
    with the words. Generic girih fills the rest.
    """
    img = _gradient(w, h)
    if use_textures:
        p = TEX / "girih.png"
        if p.exists():
            try:
                _tile(img, Image.open(p).convert("RGB").resize(
                    (max(w // 2, 320), max(h // 3, 320))), 0.16)
            except Exception:
                pass
        # topical art first (behind everything), then subtle generic ground art
        m = motif_for(topic_key)
        if m is not None:
            _ink_layer(img, m, opacity=0.42, scale=1.04, cy=0.50)
        _ink_layer(img, TEX / "arabesque.png", opacity=0.18, scale=0.90, cy=0.46)
    _vignette(img)
    _frame_border(img)
    return img


# --------------------------------------------------------------------------
# typography
# --------------------------------------------------------------------------

def f(path: Path, size: int) -> ImageFont.FreeTypeFont:
    fo = ImageFont.truetype(str(path), max(int(size), 8))
    # Noto Naskh ships variable; "NotoNaskhArabic-Bold.ttf" is that same file, so
    # the weight has to be selected explicitly.
    if "Bold" in path.name:
        for name in ("Bold", "700"):
            try:
                fo.set_variation_by_name(name)
                break
            except Exception:
                continue
    return fo


def wrap(text: str, font_: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    out, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if font_.getlength(t) <= max_w or not cur:
            cur = t
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def fit_lines(text: str, path: Path, max_w: int, max_lines: int, max_h: int,
              lh: float, hi: int, lo: int = 20) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest size where `text` fits within max_lines AND max_h."""
    for size in range(hi, lo - 1, -2):
        fx = f(path, size)
        lines = wrap(text, fx, max_w)
        if len(lines) <= max_lines and len(lines) * size * lh <= max_h:
            return fx, lines
    fx = f(path, lo)
    return fx, wrap(text, fx, max_w)[:max_lines]


#: How much thicker the ayah is drawn than the font's own weight.
#:
#: Simulation by stroke rather than by swapping to NotoNaskhArabic-Bold: the
#: ayah is set in Amiri, and Amiri has no bold. Swapping files to get weight
#: would change the typeface, which is a bigger change than anyone asked for.
#: PIL strokes the glyph outline symmetrically, so the letterforms stay Amiri
#: and only the stems thicken. Scaled with the frame width so it does not read
#: as a hairline on a 4K render and as a smear on a small one.
AR_STROKE = 0.0022


def balanced_wrap(text: str, font_: ImageFont.FreeTypeFont, max_w: int,
                  max_lines: int = 2) -> list[str]:
    """Wrap into at most `max_lines` lines of similar length.

    Greedy wrapping leaves the tail wherever it falls, so a two-line heading can
    end up with one word on its own line. This tries every split point and keeps
    the one whose longest line is shortest - which is the split that looks
    deliberate instead of accidental.
    """
    words = text.split()
    if len(words) <= 1:
        return [text] if text else []
    best: list[str] | None = None
    best_key = None
    for k in range(1, len(words)):
        cand = [" ".join(words[:k]), " ".join(words[k:])]
        if any(font_.getlength(ln) > max_w for ln in cand):
            continue
        key = max(font_.getlength(ln) for ln in cand)
        if best_key is None or key < best_key:
            best, best_key = cand, key
    if best is not None:
        return best
    return wrap(text, font_, max_w)[:max_lines]


def paint_word(frame: Image.Image, xr: int, wy: int, text: str,
               font_: ImageFont.FreeTypeFont, fill, glow: bool = False,
               glow_col=(255, 226, 160), radius: int = 15,
               alpha: int = 200, stroke: int = 0) -> None:
    """Draw one Arabic word, optionally with a soft halo (the recited word).

    The halo is built as a small RGBA patch around just this word and pasted
    back, so nothing allocates a full-canvas layer per frame - and no reliance on
    ImageDraw's private `.im` attribute, which Pillow 12 removed.
    """
    if not glow:
        ImageDraw.Draw(frame).text((xr, wy), text, font=font_, fill=fill, anchor="ra",
                                   stroke_width=stroke, stroke_fill=fill, **RTL)
        return
    bb = font_.getbbox(text, anchor="ra", **RTL)
    pad = radius * 2 + 4
    x0, y0 = int(xr + bb[0]) - pad, int(wy + bb[1]) - pad
    x1, y1 = int(xr + bb[2]) + pad, int(wy + bb[3]) + pad
    tw, th = max(x1 - x0, 1), max(y1 - y0, 1)
    patch = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    dp = ImageDraw.Draw(patch)
    ax, ay = xr - x0, wy - y0
    dp.text((ax, ay), text, font=font_, fill=(*glow_col, alpha), anchor="ra", **RTL)
    patch = patch.filter(ImageFilter.GaussianBlur(radius))
    ImageDraw.Draw(patch).text((ax, ay), text, font=font_, fill=(*fill, 255),
                               anchor="ra", stroke_width=stroke,
                               stroke_fill=(*fill, 255), **RTL)
    frame.paste(patch, (x0, y0), patch)


# --------------------------------------------------------------------------
# layout
# --------------------------------------------------------------------------

def layout_words(words: list[dict], font_: ImageFont.FreeTypeFont, max_w: int,
                 max_rows: int) -> list[list[tuple[dict, int]]]:
    rows: list[list[tuple[dict, int]]] = []
    cur: list[tuple[dict, int]] = []
    curw = 0
    gap = font_.size * 0.34
    for w in words:
        ww = int(font_.getlength(w["text"]))
        add = ww + (gap if cur else 0)
        if cur and curw + add > max_w:
            rows.append(cur)
            cur, curw = [(w, ww)], ww
        else:
            cur.append((w, ww))
            curw += add
    if cur:
        rows.append(cur)
    return rows[:max_rows] if len(rows) > max_rows else rows


#: The topic block may take at most this share of the frame height, and this is
#: the control that keeps a heading a heading. Without a budget, "make it fit"
#: simply grows the type until the header owns the card: measured on the
#: published set, quran:30:21 had a 28.4% header and a body squeezed to 47.7%,
#: and from the top edge of the frame to the first line of the verse was 38%.
HEADER_BUDGET = 0.125


def _ink_h(font_: ImageFont.FreeTypeFont, text: str) -> int:
    """Height of the pixels a string actually puts down.

    Not the same as the font size, and the difference is the whole story for
    Nastaliq: Urdu ink measures 1.88x the nominal size, English only 0.97x.
    Laying out by the nominal size therefore reserves nearly twice the height
    the Urdu needs.
    """
    bb = font_.getbbox(text)
    return int(bb[3] - bb[1]) if bb else 0


def _mm_ink_offset(font_: ImageFont.FreeTypeFont, text: str, **kw) -> float:
    """How far an `anchor="mm"` draw puts the ink from the point it was given.

    `mm` centres the font's LAYOUT box, and Nastaliq ships an enormous
    ascent/descent, so the layout centre sits well above the letters. Measuring
    the offset once per line lets every line be placed by its ink - which is
    what the eye is aligning.
    """
    tmp = Image.new("L", (8, 600), 0)
    ImageDraw.Draw(tmp).text((4, 300), text, font=font_, fill=255, anchor="mm", **kw)
    bb = tmp.getbbox()
    return ((bb[1] + bb[3]) / 2 - 300) if bb else 0.0


def _fit_topic(comp: Comp, w: int, h: int) -> tuple:
    """One type size for BOTH headlines, plus the lines each one needs.

    The rule, in order of priority:

    1. Never exceed `HEADER_BUDGET` of the frame. This is what the owner asked
       for - the verse is the content, the topic is a label.
    2. Within that budget, prefer the largest type.
    3. Prefer fewer lines: an extra line costs a fixed penalty, so a headline
       that only just wraps is not chosen over a slightly smaller one that
       sits on one line. (Without this, ibnmajah:224 jumped to 43px and two
       English lines to gain one pixel over 42px on one.)

    Returns (size, lines_en, lines_ur, h_en, h_ur).
    """
    pad = int(w * 0.085)
    inner = w - 2 * pad
    cap = int(w * 0.050)
    floor = int(w * 0.026)
    penalty = int(w * 0.0074)
    room = int(h * HEADER_BUDGET) - _TOP_PAD(w) - _BOT_PAD(w) - _H_GAP(w)

    best = None
    size = cap
    while size >= floor:
        fe, fu = f(LATIN_B, size), f(URDU, size)
        le = wrap(comp.topic_en, fe, inner) if comp.topic_en else []
        lu = wrap(comp.topic_ur, fu, inner) if comp.topic_ur else []
        if len(le) <= 2 and len(lu) <= 2:
            pe = int(size * 1.20)
            ie = max((_ink_h(fe, ln) for ln in le), default=0)
            iu = max((_ink_h(fu, ln) for ln in lu), default=0)
            pu = max(int(size * 2.05), iu)     # Urdu lines must not touch
            h_en = (len(le) - 1) * pe + ie
            h_ur = (len(lu) - 1) * pu + iu
            if h_en + h_ur <= room:
                score = size - penalty * max(len(le) + len(lu) - 2, 0)
                if best is None or score > best[0]:
                    best = (score, size, le, lu, h_en, h_ur)
        size -= 2
    if best is None:
        # A headline far longer than any we ship. Shrink to the floor and let it
        # wrap rather than overflow the frame.
        fe, fu = f(LATIN_B, floor), f(URDU, floor)
        le = wrap(comp.topic_en, fe, inner) if comp.topic_en else []
        lu = wrap(comp.topic_ur, fu, inner) if comp.topic_ur else []
        h_en = len(le) * int(floor * 1.20)
        h_ur = len(lu) * int(floor * 2.05)
        return floor, le, lu, h_en, h_ur
    _, size, le, lu, h_en, h_ur = best
    return size, le, lu, h_en, h_ur


def _TOP_PAD(w: int) -> int:
    return max(int(w * 0.013), 10)


def _BOT_PAD(w: int) -> int:
    return max(int(w * 0.010), 8)


def _H_GAP(w: int) -> int:
    return max(int(w * 0.013), 10)


def _draw_topic(d: ImageDraw.ImageDraw, comp: Comp, w: int, h: int,
                y: int) -> tuple[int, int]:
    """The on-screen topic: bold, explanatory, equal-size, and COMPACT.

    One size for both languages (that requirement is unchanged), one or two
    lines each, and never more than `HEADER_BUDGET` of the frame - see
    `_fit_topic` for how the size is chosen.

    Returns (y just past the block, the size both lines were set at).
    """
    pad = int(w * 0.085)
    size, lines_en, lines_ur, h_en, h_ur = _fit_topic(comp, w, h)
    fe, fu = f(LATIN_B, size), f(URDU, size)

    top_pad, gap, bot_pad = _TOP_PAD(w), _H_GAP(w), _BOT_PAD(w)
    block_h = top_pad + h_en + gap + h_ur + bot_pad
    plate = [pad - 24, y - top_pad, w - pad + 24, y + block_h]
    d._studio_plate = (int(plate[1]), int(plate[3]))     # read back by build_bases
    d.rounded_rectangle(plate, radius=22, fill=(0, 0, 0, 78),
                        outline=(*GOLD_DIM, 150), width=2)

    # A thin gold rule between the languages reads as "title, then subtitle".
    yr = int(y + top_pad + h_en + gap / 2)
    d.line([(w // 2 - int(w * 0.16), yr), (w // 2 + int(w * 0.16), yr)],
           fill=(*GOLD_DIM, 170), width=2)

    # Place every line by its own ink centre. `_mm_ink_offset` is what makes
    # that possible: the anchor alone would sit the Urdu well above its letters.
    pitch_en = int(size * 1.20)
    cy = y + top_pad
    for ln in lines_en:
        ink = _ink_h(fe, ln)
        d.text((w // 2, cy + ink / 2 - _mm_ink_offset(fe, ln)), ln, font=fe,
               fill=GOLD_HI, anchor="mm")
        cy += pitch_en
    cy = y + top_pad + h_en + gap
    ink_ur = max((_ink_h(fu, ln) for ln in lines_ur), default=0)
    pitch_ur = max(int(size * 2.05), ink_ur)
    for ln in lines_ur:
        d.text((w // 2, cy + ink_ur / 2 - _mm_ink_offset(fu, ln, **RTL)), ln,
               font=fu, fill=GOLD, anchor="mm", **RTL)
        cy += pitch_ur
    return int(plate[3]), size


def _draw_reference(d: ImageDraw.ImageDraw, comp: Comp, w: int, h: int) -> None:
    """Easy-to-read citation block, bottom."""
    pad = int(w * 0.085)
    # Readability rule: a citation nobody can read on a phone is not a citation.
    # 36 px on a 1080-wide frame, comfortably above the "squint" threshold.
    fe = f(LATIN_B, int(w * 0.0335))
    fa = f(UI, int(w * 0.0345))
    fg = f(LATIN, int(w * 0.0235))
    grade = (comp.grade or "").strip()
    box_h = int(fe.size * 3.15) + (int(fg.size * 2.0) if grade else 0)
    y0 = h - int(h * 0.055) - box_h
    d.rounded_rectangle([pad - 14, y0, w - pad + 14, y0 + box_h], radius=16,
                        fill=(0, 0, 0, 86), outline=(*GOLD_DIM, 170), width=2)
    cy = y0 + int(box_h * 0.27)
    if comp.reference_ar:
        d.text((w // 2, cy), comp.reference_ar, font=fa, fill=GOLD, anchor="mm",
               **RTL)
        cy += int(fa.size * 1.30)
    d.text((w // 2, cy), comp.reference_en, font=fe, fill=GOLD_HI, anchor="mm")
    if grade:
        # A hadith shown without its grading invites the reader to assume the
        # strongest one. Where a collection ranges across grades, the frame says
        # so, in the same block as the citation.
        d.text((w // 2, cy + int(fe.size * 1.34)), grade, font=fg, fill=MUTED,
               anchor="mm")


# --------------------------------------------------------------------------
# bases
# --------------------------------------------------------------------------

def build_bases(comp: Comp) -> tuple[Image.Image, Image.Image, dict, Image.Image]:
    w, h = comp.width, comp.height
    bg = background(w, h, comp.textures, comp.topic_key)
    pad = int(w * 0.085)
    inner = w - 2 * pad

    top_y = int(h * 0.040)
    probe = ImageDraw.Draw(bg, "RGBA")
    header_bottom, heading_size = _draw_topic(probe, comp, w, h, top_y)
    _draw_reference(probe, comp, w, h)

    # The gap between the header plate and the body used to be 4.5% of the
    # frame, which the eye reads as part of the header. It is air, not content.
    body_top = header_bottom + int(h * 0.026)
    ref_h = int(w * 0.0335 * 3.15) + (int(w * 0.0235 * 2.0)
                                      if (comp.grade or "").strip() else 0)
    body_bottom = h - int(h * 0.055) - ref_h - int(h * 0.030)
    body_h = body_bottom - body_top
    _body_scrim(bg, body_top, body_bottom, pad)

    meta: dict = {"ar_stroke": max(int(w * AR_STROKE), 1),
                 "heading_size": heading_size,
                 # The whole vertical budget in one place. Every "is the
                 # heading too big?" question is answered here rather than by
                 # guessing from a frame, and tests/test_design.py pins it.
                 "geometry": {"header_top": int(getattr(probe, "_studio_plate",
                                                        (0, 0))[0]),
                              "header_bottom": header_bottom,
                              "body_top": body_top, "body_bottom": body_bottom}}

    # ---- phase 1 base -----------------------------------------------------
    # Two modes, one renderer:
    #   timed    - Qur'an: words carry recitation timings, so they are revealed
    #              one at a time (handled by the frame loop)
    #   static   - hadith: the source publishes no per-word audio, so the text is
    #              set whole and held. It is never trimmed; the isnad is part of
    #              the record and stays on the card.
    words = comp.arabic_words
    placed: list[list] = []
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)

    if words:
        size = int(w * 0.100)
        fa = f(ARABIC, size)
        rows = layout_words(words, fa, inner, 7)
        lh_f = 1.86
        while size > int(w * 0.030) and (len(rows) > 7 or
                                        len(rows) * size * lh_f > body_h):
            size -= 3
            fa = f(ARABIC, size)
            rows = layout_words(words, fa, inner, 9)

        gap = size * 0.34
        lh = int(size * lh_f)
        y = 0
        for row in rows:
            total = sum(ww for _, ww in row) + gap * (len(row) - 1)
            xr = int(w / 2 + total / 2)
            for wpair, ww in row:
                placed.append([wpair, xr, y, ww])
                xr -= ww + gap
            y += lh
        astroke = meta["ar_stroke"]
        for wpair, xr, wy, _ in placed:
            dl.text((xr, wy), wpair["text"], font=fa, fill=(*AR_DIM, 255),
                    stroke_width=astroke, stroke_fill=(*AR_DIM, 255),
                    anchor="ra", **RTL)
        meta["arabic_size"] = size
        meta["row_count"] = len(rows)
    elif comp.body_arabic:
        # A hadith arrives whole, isnad included, so the text is long by nature.
        # Give it a wider measure and more lines before shrinking the type.
        #
        # The line count must not be the binding constraint: an isnad runs to
        # several hundred characters, and capping the lines at 22 also capped the
        # type at 64 px, which left a 600 px block sitting in a 1070 px stage with
        # the reader squinting at it on a phone. Let the stage HEIGHT be the
        # constraint and allow as many lines as that needs.
        wide = int(w * 0.055) * 2
        fa, lines = fit_lines(comp.body_arabic, ARABIC, w - wide, 30, body_h, 1.40,
                              hi=int(w * 0.085))
        lh = int(fa.size * 1.42)
        astroke = meta["ar_stroke"]
        for i, ln in enumerate(lines):
            dl.text((w // 2, i * lh), ln, font=fa, fill=IVORY, anchor="ma",
                    stroke_width=astroke, stroke_fill=IVORY, **RTL)
        meta["arabic_size"] = fa.size
        meta["row_count"] = len(lines)

    # Centre on the ink that is actually there, not on the layout box: Amiri's
    # stacked diacritics make the two differ by a surprising amount, and the
    # first version of this card looked top-heavy because of it.
    bb = layer.getbbox()
    dy = dx = 0
    if bb:
        dy = (body_top + body_bottom) // 2 - (bb[1] + bb[3]) // 2
        dx = w // 2 - (bb[0] + bb[2]) // 2
        for it in placed:
            it[1] += dx
            it[2] += dy
        shifted = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shifted.paste(layer, (dx, dy), layer)
        layer = shifted
    p1 = Image.alpha_composite(bg.convert("RGBA"), layer).convert("RGB")

    p1_done = p1.copy()          # same card, every word now fully recited
    if placed:
        dd = ImageDraw.Draw(p1_done)
        fa = f(ARABIC, meta["arabic_size"])
        for wpair, xr, wy, _ in placed:
            dd.text((xr, wy), wpair["text"], font=fa, fill=AR_DONE, anchor="ra",
                    **RTL)

    meta["word_layout"] = placed

    # ---- phase 2 base: the meaning, centred the same way -------------------
    # Drawn to its own layer first so the block can be centred on real ink. A
    # one-line translation set from the top of the frame reads as a mistake.
    layer2 = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(layer2)
    y = 0
    # The two translations share the body as EQUAL HALVES, Urdu over English,
    # each block centred inside its own half. Previously the English was capped
    # at 30% of the body while the Urdu took 86%, so the English came out small
    # and low and the layout looked top-heavy. Zoning it fixes both at once: a
    # long English simply wraps into the room it has, instead of shrinking.
    rule = int(h * 0.020)          # the gold rule between the halves
    half_h = (body_h - rule) // 2
    top_half = body_top
    bot_half = body_top + half_h + rule

    def _block(text: str, path: Path, zone_top: int, zone_h: int, lh: float,
               lo: int, max_lines: int, fill, anchor: str) -> int:
        if not text:
            return 0
        fnt, lines = fit_lines(text, path, inner, max_lines, int(zone_h * 0.94),
                               lh, hi=int(w * 0.052), lo=lo)
        block = int(len(lines) * fnt.size * lh)
        cy = zone_top + (zone_h - block) // 2        # centred in its own half
        for ln in lines:
            if anchor == "mm":
                d2.text((w // 2, cy + fnt.size * 0.5), ln, font=fnt, fill=fill,
                        anchor="mm", **RTL)
            else:
                d2.text((w // 2, cy), ln, font=fnt, fill=fill, anchor="ma")
            cy += int(fnt.size * lh)
        return fnt.size

    if comp.urdu:
        meta["urdu_size"] = _block(comp.urdu, URDU, top_half, half_h, 2.10,
                                   lo=22, max_lines=8, fill=IVORY, anchor="mm")
    if comp.english:
        yrule = top_half + half_h + rule // 2
        d2.line([(w // 2 - int(w * 0.13), yrule), (w // 2 + int(w * 0.13), yrule)],
                fill=(*GOLD_DIM, 190), width=2)
        meta["english_size"] = _block(comp.english, LATIN, bot_half, half_h, 1.34,
                                      lo=18, max_lines=8, fill=MUTED, anchor="ma")
    bb2 = layer2.getbbox()
    if bb2:
        dy2 = (body_top + body_bottom) // 2 - (bb2[1] + bb2[3]) // 2
        sh2 = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sh2.paste(layer2, (0, dy2), layer2)
        layer2 = sh2
    p2 = Image.alpha_composite(bg.convert("RGBA"), layer2).convert("RGB")

    return p1, p2, meta, p1_done


# --------------------------------------------------------------------------
# frame loop
# --------------------------------------------------------------------------

def render(comp: Comp, out_audio: Path, out_path: Path, work: Path | None = None,
           verbose: bool = True) -> dict:
    work = work or Path("output/studio")
    work.mkdir(parents=True, exist_ok=True)
    p1, p2, meta, p1_done = build_bases(comp)
    fa = f(ARABIC, meta.get("arabic_size", 90))
    astroke = meta.get("ar_stroke", 2)
    w, h, fps = comp.width, comp.height, comp.fps
    laid = meta["word_layout"]

    n1 = int(comp.phase1 * fps)
    n2 = int(comp.phase2 * fps)
    n_total = n1 + n2
    cf = max(int(comp.crossfade * fps), 1)
    total = comp.total

    # The output duration is stated twice on purpose, and it is NOT `-shortest`.
    #
    # The audio tail used to be a bare `apad`, which pads with silence forever.
    # With `-shortest`, ffmpeg then never saw EOF on the audio side and the encode
    # hung after the last frame was already written - measured: still running at
    # 32 s on a 5 s clip, and it silently ate a whole session before that. Bounding
    # the pad with `whole_dur` plus an explicit `-t` finishes the same clip in 2.6 s.
    audio_fc = (f"[1:a]aresample=44100,loudnorm=I=-15:TP=-1.5:LRA=11,"
                f"apad=whole_dur={total:.3f}[a]")

    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-i", str(out_audio),
           "-filter_complex",
           "[0:v]fps=" + str(fps) + ",format=yuv420p[v];" + audio_fc,
           "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           "-movflags", "+faststart", str(out_path)]
    # stderr goes to a file, not a pipe: a pipe nobody drains can block ffmpeg,
    # and at -v error there is nothing to stream anyway. Reading it afterwards is
    # what turns "it hung" into an actual error message.
    log = work / "render.log"
    log_fh = open(log, "wb")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log_fh)

    # A hang must cost a bounded amount of the session, never all of it.
    deadline = time.time() + max(240.0, total * 15.0 + 120.0)

    def _drain_and_fail(why: str):
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.stdin.close()
        except Exception:
            pass
        log_fh.close()
        tail = ""
        try:
            tail = log.read_text("utf-8", "replace").strip()[-900:]
        except Exception:
            pass
        raise RuntimeError(f"{why} (see {log})\n{tail}")

    starts = [(comp.lead + it[0]["start"]) * fps for it in laid]
    ends = [(comp.lead + it[0]["end"]) * fps for it in laid]

    try:
        for fr in range(n_total):
            t = fr / fps
            if fr < n1 - cf:
                frame = p1.copy()
                dd = ImageDraw.Draw(frame)
                active = None
                for i, it in enumerate(laid):
                    if fr >= ends[i]:
                        # already recited: keep it, in full gold
                        dd.text((it[1], it[2]), it[0]["text"], font=fa,
                                fill=AR_DONE, anchor="ra",
                                stroke_width=astroke, stroke_fill=AR_DONE, **RTL)
                    elif fr >= starts[i]:
                        active = it
                if active is not None:
                    paint_word(frame, active[1], active[2], active[0]["text"], fa,
                               GOLD_HI, glow=True, stroke=astroke)
            elif fr < n1:
                mix = (fr - (n1 - cf)) / cf
                frame = Image.blend(p1_done, p2, mix)
            else:
                frame = p2.copy() if fr > n1 + cf else Image.blend(
                    p1_done, p2, min((fr - n1) / cf, 1.0))
            if fr % 30 == 0 and time.time() > deadline:
                _drain_and_fail(f"render exceeded its time budget at frame "
                                f"{fr}/{n_total}")
            proc.stdin.write(frame.tobytes())
            if verbose and fr % (fps * 5) == 0:
                print("  [studio] %5.1fs / %.1fs  %4.0f%%"
                      % (t, total, 100.0 * fr / max(n_total, 1)), flush=True)
    except BrokenPipeError:
        _drain_and_fail("ffmpeg closed the frame pipe early")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
    try:
        proc.wait(timeout=max(180.0, total * 4.0))
    except subprocess.TimeoutExpired:
        _drain_and_fail("ffmpeg did not exit after the last frame")
    log_fh.close()
    if proc.returncode != 0:
        tail = log.read_text("utf-8", "replace").strip()[-900:]
        raise RuntimeError(f"ffmpeg exited {proc.returncode} (see {log})\n{tail}")

    dur = _dur(out_path)
    return {"file": str(out_path), "seconds": round(dur, 2),
            "size_mb": round(out_path.stat().st_size / 1e6, 2),
            "frames": n_total, "arabic_size": meta.get("arabic_size")}


def _dur(p: Path) -> float:
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True,
                       text=True).stdout.strip()
    try:
        return float(o)
    except ValueError:
        return 0.0
