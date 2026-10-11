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
AR_DIM = (120, 146, 138)
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
    ImageDraw.Draw(m).rounded_rectangle(
        [pad - 20, top - 40, w - pad + 20, bottom + 40], radius=90, fill=88)
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


def paint_word(frame: Image.Image, xr: int, wy: int, text: str,
               font_: ImageFont.FreeTypeFont, fill, glow: bool = False,
               glow_col=(255, 226, 160), radius: int = 15,
               alpha: int = 200) -> None:
    """Draw one Arabic word, optionally with a soft halo (the recited word).

    The halo is built as a small RGBA patch around just this word and pasted
    back, so nothing allocates a full-canvas layer per frame - and no reliance on
    ImageDraw's private `.im` attribute, which Pillow 12 removed.
    """
    if not glow:
        ImageDraw.Draw(frame).text((xr, wy), text, font=font_, fill=fill, anchor="ra",
                                   **RTL)
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
                               anchor="ra", **RTL)
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


def _draw_topic(d: ImageDraw.ImageDraw, comp: Comp, w: int, y: int) -> int:
    """The on-screen topic: explanatory, bold, ONE line per language.

    Two lines total - an English line and an Urdu line. Each auto-shrinks until
    it fits a single line, so a longer headline loses size, never structure.
    Returns the y coordinate just past the block.
    """
    pad = int(w * 0.085)
    inner = w - 2 * pad

    fe, lines_en = fit_lines(comp.topic_en, LATIN_B, inner, 1, int(w * 0.10), 1.16,
                             hi=int(w * 0.053))
    fu = f(URDU, 20)
    lines_ur: list[str] = []
    if comp.topic_ur:
        fu, lines_ur = fit_lines(comp.topic_ur, URDU, inner, 1, int(w * 0.16), 2.6,
                                 hi=int(w * 0.070))

    top_pad = int(w * 0.020)
    gap = int(w * 0.022)
    h_en = int(fe.size * 1.16)
    h_ur = int(fu.size * 2.6) if lines_ur else 0
    block_h = top_pad + h_en + gap + h_ur + int(w * 0.016)
    plate = [pad - 24, y - top_pad, w - pad + 24, y + block_h]
    d.rounded_rectangle(plate, radius=22, fill=(0, 0, 0, 78),
                        outline=(*GOLD_DIM, 150), width=2)
    # a thin gold rule under the English line reads as "title, then subtitle"
    yr = y + h_en + gap // 2
    d.line([(w // 2 - int(w * 0.16), yr), (w // 2 + int(w * 0.16), yr)],
           fill=(*GOLD_DIM, 170), width=2)

    cy = y + top_pad
    for ln in lines_en:
        d.text((w // 2, cy + h_en * 0.5), ln, font=fe, fill=GOLD_HI, anchor="mm")
    cy += h_en + gap
    for ln in lines_ur:
        d.text((w // 2, cy + h_ur * 0.5), ln, font=fu, fill=GOLD, anchor="mm", **RTL)
    return int(plate[3])


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

    top_y = int(h * 0.062)
    probe = ImageDraw.Draw(bg, "RGBA")
    header_bottom = _draw_topic(probe, comp, w, top_y)
    _draw_reference(probe, comp, w, h)

    body_top = header_bottom + int(h * 0.045)
    ref_h = int(w * 0.0335 * 3.15) + (int(w * 0.0235 * 2.0)
                                      if (comp.grade or "").strip() else 0)
    body_bottom = h - int(h * 0.055) - ref_h - int(h * 0.030)
    body_h = body_bottom - body_top
    _body_scrim(bg, body_top, body_bottom, pad)

    meta: dict = {}

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
        for wpair, xr, wy, _ in placed:
            dl.text((xr, wy), wpair["text"], font=fa, fill=(*AR_DIM, 255),
                    anchor="ra", **RTL)
        meta["arabic_size"] = size
        meta["row_count"] = len(rows)
    elif comp.body_arabic:
        # A hadith arrives whole, isnad included, so the text is long by nature.
        # Give it a wider measure and more lines before shrinking the type.
        wide = int(w * 0.055) * 2
        fa, lines = fit_lines(comp.body_arabic, ARABIC, w - wide, 22, body_h, 1.40,
                              hi=int(w * 0.060))
        lh = int(fa.size * 1.42)
        for i, ln in enumerate(lines):
            dl.text((w // 2, i * lh), ln, font=fa, fill=IVORY, anchor="ma", **RTL)
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
    if comp.urdu:
        fu, lines = fit_lines(comp.urdu, URDU, inner, 10, int(body_h * 0.86), 2.42,
                              hi=int(w * 0.058))
        for ln in lines:
            d2.text((w // 2, y + fu.size * 0.5), ln, font=fu, fill=IVORY,
                    anchor="mm", **RTL)
            y += int(fu.size * 2.42)
        meta["urdu_size"] = fu.size
    if comp.english:
        y += int(h * 0.012)
        d2.line([(w // 2 - int(w * 0.13), y), (w // 2 + int(w * 0.13), y)],
                fill=(*GOLD_DIM, 190), width=2)
        y += int(h * 0.015)
        fe, lines = fit_lines(comp.english, LATIN, inner, 6, int(body_h * 0.30), 1.5,
                              hi=int(w * 0.030))
        for ln in lines:
            d2.text((w // 2, y), ln, font=fe, fill=MUTED, anchor="ma")
            y += int(fe.size * 1.5)
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
    w, h, fps = comp.width, comp.height, comp.fps
    laid = meta["word_layout"]

    n1 = int(comp.phase1 * fps)
    n2 = int(comp.phase2 * fps)
    n_total = n1 + n2
    cf = max(int(comp.crossfade * fps), 1)

    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-i", str(out_audio),
           "-filter_complex",
           "[0:v]fps=" + str(fps) + ",format=yuv420p[v];[1:a]aresample=44100,"
           "loudnorm=I=-15:TP=-1.5:LRA=11,apad[a]",
           "-map", "[v]", "-map", "[a]", "-shortest",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

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
                                fill=AR_DONE, anchor="ra", **RTL)
                    elif fr >= starts[i]:
                        active = it
                if active is not None:
                    paint_word(frame, active[1], active[2], active[0]["text"], fa,
                               GOLD_HI, glow=True)
            elif fr < n1:
                mix = (fr - (n1 - cf)) / cf
                frame = Image.blend(p1_done, p2, mix)
            else:
                frame = p2.copy() if fr > n1 + cf else Image.blend(
                    p1_done, p2, min((fr - n1) / cf, 1.0))
            proc.stdin.write(frame.tobytes())
            if verbose and fr % (fps * 5) == 0:
                print("  [studio] %5.1fs / %.1fs" % (t, n_total / fps), flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed while writing frames")

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
