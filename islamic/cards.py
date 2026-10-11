"""
Card renderer - Arabic + Urdu + English text cards as PNG.

Uses PIL with **libraqm** (verified present, v0.10.5), which does Arabic
shaping and bidi natively. This matters more than anything else in the
renderer: unshaped Arabic renders as disconnected isolated letters, which for
Quranic text is not a cosmetic bug but a corruption of the text.

Fonts (assets/fonts/, all SIL OFL or public):
  Amiri              - classical Naskh, the Arabic display face
  NotoNastaliqUrdu   - the Urdu face
  NotoNaskhArabic    - Arabic UI / bold accents
  DejaVuSans         - Latin, because PIL does NO font fallback: handing Latin
                       text to an Arabic-only font renders tofu boxes

Layout rule learned the hard way: the footer is reserved FIRST and text is fit
into the space that remains. Drawing the footer at a fixed y and hoping the body
clears it produced overlapping, clipped cards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"

ARABIC_FONT = FONTS / "Amiri-Regular.ttf"
URDU_FONT = FONTS / "NotoNastaliqUrdu-Regular.ttf"
UI_FONT = FONTS / "NotoNaskhArabic-Regular.ttf"
LATIN_FONT = FONTS / "DejaVuSans.ttf"
LATIN_BOLD = FONTS / "DejaVuSans-Bold.ttf"

RTL = {"direction": "rtl", "language": "ar"}

# Nastaliq stacks far taller than its point size; Naskh less so.
LINE_H = {"arabic": 1.95, "urdu": 2.65, "latin": 1.55}


@dataclass
class Theme:
    bg: tuple[int, int, int] = (9, 26, 22)
    bg2: tuple[int, int, int] = (14, 43, 36)
    gold: tuple[int, int, int] = (217, 177, 105)
    gold_dim: tuple[int, int, int] = (150, 120, 66)
    ink: tuple[int, int, int] = (238, 246, 242)
    dim: tuple[int, int, int] = (158, 186, 178)
    arabic: tuple[int, int, int] = (240, 212, 154)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), max(size, 8))


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if f.getlength(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, path: Path, max_w: int, max_h: int, lh: float,
        hi: int = 130, lo: int = 18) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest size at which the wrapped text fits the given box."""
    best = None
    for size in range(hi, lo - 1, -2):
        f = font(path, size)
        lines = wrap(text, f, max_w)
        if len(lines) * f.size * lh <= max_h:
            best = (f, lines)
            break
    if best is None:
        f = font(path, lo)
        best = (f, wrap(text, f, max_w))
    return best


def _lattice(d: ImageDraw.ImageDraw, w: int, h: int, theme: Theme,
             step: int = 150, alpha: int = 22) -> None:
    """Faint eight-point star lattice — geometric, never figurative."""
    col = (*theme.gold, alpha)
    m = step * 0.30
    for y in range(step // 2, h + step, step):
        for x in range(step // 2, w + step, step):
            pts = []
            for k in range(16):
                r = m if k % 2 == 0 else m * 0.44
                a = k * math.pi / 8
                pts.append((x + r * math.cos(a), y + r * math.sin(a)))
            d.polygon(pts, outline=col)


def render_card(
    size: tuple[int, int],
    arabic: str = "",
    urdu: str = "",
    english: str = "",
    source: str = "",
    source_ar: str = "",
    topic: str = "",
    theme: Theme | None = None,
    show_pattern: bool = True,
) -> Image.Image:
    w, h = size
    th = theme or Theme()
    img = Image.new("RGB", (w, h), th.bg)
    d = ImageDraw.Draw(img, "RGBA")

    for y in range(h):
        t = y / max(h - 1, 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(th.bg[i] + (th.bg2[i] - th.bg[i]) * t) for i in range(3)))
    if show_pattern:
        _lattice(d, w, h, th)

    pad = int(w * 0.085)
    inner_w = w - 2 * pad
    top = int(h * 0.070)

    # ---- reserve the footer BEFORE fitting any text ----------------------
    footer_h = 0
    footer_y = h - pad
    if source:
        fs = font(LATIN_FONT, int(w * 0.030))
        footer_h = int(fs.size * 2.5)
        footer_y = h - pad - footer_h

    # ---- topic chip (Latin) ----------------------------------------------
    if topic:
        f = font(LATIN_BOLD, int(w * 0.026))
        label = topic.upper()
        tw = f.getlength(label)
        ch = int(w * 0.052)
        d.rounded_rectangle([(w // 2 - tw / 2 - 30, top), (w // 2 + tw / 2 + 30, top + ch)],
                            radius=ch // 2, outline=th.gold_dim, width=2)
        d.text((w // 2, top + ch / 2), label, font=f, fill=th.gold, anchor="mm")
        top += ch + int(h * 0.030)

    avail = footer_y - top - int(h * 0.020)
    if avail < h * 0.15:
        avail = int(h * 0.15)

    blocks: list[tuple[str, str, Path, int]] = []
    if arabic:
        blocks.append(("arabic", arabic, ARABIC_FONT, int(w * 0.098)))
    if urdu:
        blocks.append(("urdu", urdu, URDU_FONT, int(w * 0.064)))
    if english:
        blocks.append(("latin", english, LATIN_FONT, int(w * 0.031)))

    # weight the vertical budget: Arabic is the hero, Urdu the translation,
    # English a caption. Latin wraps to more lines so it gets a smaller share.
    gate = {"arabic": 1.0, "urdu": 0.92, "latin": 0.55}
    total_gate = sum(gate[b[0]] for b in blocks) or 1.0
    divider_h = int(h * 0.055)
    body_avail = avail - divider_h * max(len(blocks) - 1, 0)

    rendered: list[tuple[str, ImageFont.FreeTypeFont, list[str]]] = []
    for kind, text, path, hi in blocks:
        budget = int(body_avail * gate[kind] / total_gate)
        f, lines = fit(text, path, inner_w, budget,
                       LINE_H["arabic" if kind == "arabic" else
                              "urdu" if kind == "urdu" else "latin"], hi=hi)
        rendered.append((kind, f, lines))

    # ---- draw -------------------------------------------------------------
    # Centre the body vertically in the space between the chip and the footer.
    # Drawing from `top` left tall cards with dead space at the bottom.
    block_heights = []
    for kind, f, lines in rendered:
        lh = int(f.size * LINE_H["arabic" if kind == "arabic" else
                                 "urdu" if kind == "urdu" else "latin"])
        block_heights.append(len(lines) * lh)
    drawn_h = sum(block_heights) + divider_h * max(len(rendered) - 1, 0)
    y = top + max(int((avail - drawn_h) / 2), 0)

    for i, (kind, f, lines) in enumerate(rendered):
        lh = int(f.size * LINE_H["arabic" if kind == "arabic" else
                                 "urdu" if kind == "urdu" else "latin"])
        colour = th.arabic if kind == "arabic" else (th.ink if kind == "urdu" else th.dim)
        for ln in lines:
            if kind == "latin":
                d.text((w // 2, y), ln, font=f, fill=colour, anchor="ma")
            else:
                d.text((w - pad, y), ln, font=f, fill=colour, anchor="ra", **RTL)
            y += lh
        # only advance past what was actually used, then add the divider
        if i < len(rendered) - 1:
            cy = y + int(h * 0.014)
            d.line([(pad, cy), (w // 2 - 24, cy)], fill=th.gold_dim, width=2)
            d.line([(w // 2 + 24, cy), (w - pad, cy)], fill=th.gold_dim, width=2)
            d.polygon([(w // 2, cy - 8), (w // 2 + 12, cy), (w // 2, cy + 8),
                       (w // 2 - 12, cy)], outline=th.gold, width=2)
            y = cy + int(h * 0.030)

    # ---- footer -----------------------------------------------------------
    if source:
        fs = font(LATIN_FONT, int(w * 0.030))
        d.rounded_rectangle([(pad, footer_y), (w - pad, footer_y + footer_h)],
                            radius=int(w * 0.018), fill=(0, 0, 0, 70),
                            outline=th.gold_dim, width=1)
        d.text((w // 2, footer_y + footer_h * 0.30), source, font=fs,
               fill=th.gold, anchor="mm")
        if source_ar:
            fa = font(ARABIC_FONT, int(w * 0.030))
            d.text((w // 2, footer_y + footer_h * 0.70), source_ar, font=fa,
                   fill=th.gold_dim, anchor="mm", **RTL)
    return img


def write_card(path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    render_card(**kw).save(p, "PNG", optimize=True)
    return p
