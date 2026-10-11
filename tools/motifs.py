"""
The 2D motif set — what each topic's background art is, and why.

Every motif is gold linework on a dark ground, generated to a written prompt so
the set can be re-drawn or extended without guesswork. The renderer turns each
one into gold ink directly (see studio._ink_layer) rather than pasting the image,
so the artwork never brings its own rectangle onto the frame.

Rules the prompts encode, and why:
  geometric and botanical only — no figurative imagery, which the tradition
  rules out for a devotional frame;
  nothing that could read as calligraphy or as a letter, because a stray glyph
  next to real Qur'anic text is a serious error;
  matched stroke weight and palette, so a new motif drops straight into the set;
  centred with wide margins, so it survives being placed behind type.

    python tools/motifs.py             # report which topics have art
    python tools/motifs.py --prompts   # print the prompts (feed to a generator)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "assets" / "motifs"

STYLE = (
    "drawn as fine gold linework on a pure flat dark teal-green background "
    "(#0b241c). Strictly geometric and botanical, absolutely no human figures, "
    "no faces, no animals, no calligraphy, no letters, no text. Symmetrical, "
    "centred, generous empty dark space around the motif, thin 2-pixel gold "
    "strokes, ornamental certificate style, crisp edges, screen-print flatness, "
    "no gradient meshes, no texture noise, no border, no frame."
)

SUBJECTS: dict[str, str] = {
    "marriage": "A single flat 2D vector ornament for the concept of marriage: two "
                "elegant interlocking gold rings at the centre, from which "
                "symmetrical Islamic islimi scrollwork grows outward, plus two "
                "mirrored stylised date-palm fronds.",
    "children": "A single flat 2D vector ornament for the concept of children and "
                "family: one large eight-pointed Islamic star at the centre with "
                "three much smaller eight-pointed stars orbiting it closely like "
                "satellites on a thin circular orbit line, symmetric islimi vines "
                "growing between them, and a stylised pomegranate motif at the base.",
    "daughters": "A single flat 2D vector ornament for the concept of a cherished "
                 "daughter: an eight-pointed Islamic star at the centre cradled "
                 "inside an open protective arc, two small delicate eight-pointed "
                 "stars resting inside the arc as if sheltered, gentle symmetric "
                 "islimi vine leaves radiating outward.",
    "business": "A single flat 2D vector ornament for the concept of honest trade "
                "and fair dealing: a perfectly balanced geometric beam scale whose "
                "fulcrum is an eight-pointed Islamic star, two hanging pans drawn as "
                "geometric semi-circles, a coin rosette medallion on either side, "
                "symmetric islimi scrollwork growing outward.",
    "women": "A single flat 2D vector ornament for the concept of the dignity and "
             "rights of women: two perfectly identical geometric jewelled medallions "
             "at exactly equal height side by side, each a nested eight-pointed star "
             "within a ring, joined by a horizontal bar of equal length, with a "
             "mirrored pair of stylised lotus flowers rising from between them. "
             "Balance and parity are the whole idea.",
    "parents": "A single flat 2D vector ornament for the concept of honouring elderly "
               "parents: two tall elegant geometric arborescent forms standing side "
               "by side, each grown from a shared symmetrical root system at the "
               "base, their branches arching gently inward toward each other to form "
               "a protective canopy over a small eight-pointed star suspended beneath "
               "them.",
    "knowledge": "A single flat 2D vector ornament for the concept of knowledge and "
                 "the qalam pen: a stylised geometric reed pen diagonally crossing a "
                 "multi-pointed Islamic star, with an open geometric page form and "
                 "symmetric islimi scrollwork radiating from the centre.",
    "prayer": "A single flat 2D vector ornament for the concept of supplication and "
              "du'a: two open cupped geometric hands drawn as abstract symmetric "
              "crescent shapes rising from a stylised mihrab arch, with a thin "
              "elegant eight-pointed star floating in the space above them and "
              "symmetric islimi scrollwork radiating outward. The hands are purely "
              "abstract geometry, no human face, no detailed fingers, no figure.",
}


def prompt_for(topic: str) -> str:
    return SUBJECTS[topic] + " " + STYLE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", action="store_true",
                    help="print generator prompts, one per line as 'topic<TAB>prompt'")
    a = ap.parse_args()

    if a.prompts:
        for t in sorted(SUBJECTS):
            print(f"{t}\t{prompt_for(t)}")
        return 0

    have, missing = [], []
    for t in sorted(SUBJECTS):
        (have if (DIR / f"{t}.png").exists() else missing).append(t)
    print(f"[motifs] {len(have)}/{len(SUBJECTS)} topics have art in {DIR.relative_to(ROOT)}")
    if have:
        print("  drawn   : " + ", ".join(have))
    if missing:
        print("  missing : " + ", ".join(missing))
        print("            topics without art fall back to the generic islimi layer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
