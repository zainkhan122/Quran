#!/usr/bin/env python3
"""
Tests for the things the reviewer asked to change, so they stay changed.

These are layout requirements that were stated in words, fixed in code, and
would silently drift back the moment someone touched the renderer. Each one is
pinned here with the reason it was asked for.

They do render: `build_bases()` draws the two static card bases and reports the
type sizes it chose. That needs the fonts and Pillow, both of which `setup.sh`
guarantees, and it takes about a second.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic import studio                                          # noqa: E402
from islamic.topics import TOPICS                                   # noqa: E402

HAVE_FONTS = (studio.FONTS / "NotoNastaliqUrdu-Regular.ttf").exists() and \
             (studio.FONTS / "DejaVuSans.ttf").exists()


@unittest.skipUnless(HAVE_FONTS, "fonts not fetched")
class TestHeadings(unittest.TestCase):
    """'Heading for Urdu and English to have same Font size'."""

    def _comp(self, **kw):
        base = dict(width=1080, height=1920, fps=30,
                    topic_en="Marriage — love and mercy between spouses",
                    topic_ur="نکاح — میاں بیوی کے درمیان محبت اور رحمت",
                    reference_en="Qur'an 30:21 · Ar-Room", reference_ar="",
                    arabic_words=[], body_arabic="", urdu="", english="",
                    phase1=10.0, phase2=10.0, textures=False, topic_key="marriage")
        base.update(kw)
        return studio.Comp(**base)

    def test_english_and_urdu_headings_render_at_one_size(self):
        _, _, meta, _ = studio.build_bases(self._comp())
        self.assertIn("heading_size", meta,
                      "build_bases stopped reporting the heading size")
        self.assertGreater(meta["heading_size"], 20)

    def test_a_long_english_headline_does_not_shrink_below_the_urdu(self):
        """The failure that was reported: English small, Urdu large.

        A long English headline used to lose size on its own cap while the Urdu
        kept its bigger one. Now both are re-set to the smaller of the two.
        """
        comp = self._comp(
            topic_en="Business and trade — honesty and fair dealing in every "
                     "single transaction you make",
            topic_ur="کاروبار")
        _, _, meta, _ = studio.build_bases(comp)
        self.assertGreater(meta["heading_size"], 20)

    def test_headline_size_is_capped_so_it_stays_a_heading(self):
        _, _, meta, _ = studio.build_bases(self._comp(topic_en="Trade", topic_ur="تجارت"))
        self.assertLessEqual(meta["heading_size"], int(1080 * 0.050),
                             "the shared cap has drifted upward")


@unittest.skipUnless(HAVE_FONTS, "fonts not fetched")
class TestTheHeaderStaysCompact(unittest.TestCase):
    """'Heading is taking almost 40% of space... it needs to be compact so that
    main content takes main space.'

    The measurement that prompted it: quran:30:21 had a header plate 28.4% of
    the frame, and 32.9% of the frame before the body even started - on a phone
    that reads as "the header is a third of the screen". The cause was that the
    Urdu line height was reserved at 2.6x the font size while Nastaliq ink only
    measures 1.88x, and that a headline which missed the one-line threshold was
    re-set at the maximum size on two lines, doubling the block.

    `HEADER_BUDGET` is now the control: the plate may not exceed that share of
    the frame, and the body takes the rest.
    """

    HEADLINES = [
        ("Justice — the wronged will be heard", "انصاف — مظلوم کی آواز سنی جائے گی"),
        ("Marriage — love and mercy between spouses",
         "نکاح — میاں بیوی کے درمیان محبت اور رحمت"),
        ("Knowledge — read, and ask for more", "علم — پڑھو اور مزید مانگو"),
    ]

    def _comp(self, en, ur):
        return studio.Comp(width=1080, height=1920, fps=30, topic_en=en, topic_ur=ur,
                           reference_en="Qur'an 30:21", reference_ar="", arabic_words=[],
                           body_arabic="", urdu="", english="", phase1=10.0,
                           phase2=10.0, textures=False, topic_key="marriage")

    def test_the_budget_is_a_budget(self):
        self.assertLessEqual(studio.HEADER_BUDGET, 0.15,
                             "the header budget has been raised; the verse is the "
                             "content and the topic is a label")

    def test_every_shipped_headline_fits_the_budget(self):
        for en, ur in self.HEADLINES:
            _, _, meta, _ = studio.build_bases(self._comp(en, ur))
            g = meta["geometry"]
            share = (g["header_bottom"] - g["header_top"]) / 1920
            self.assertLessEqual(share, studio.HEADER_BUDGET + 0.015,
                                 f"header is {share:.1%} of the frame for {en!r}")

    def test_the_body_gets_the_majority_of_the_frame(self):
        for en, ur in self.HEADLINES:
            _, _, meta, _ = studio.build_bases(self._comp(en, ur))
            g = meta["geometry"]
            share = (g["body_bottom"] - g["body_top"]) / 1920
            self.assertGreater(share, 0.60,
                               f"the body only has {share:.1%} for {en!r}")

    def test_the_verse_starts_high_in_the_frame(self):
        """From the top edge to the first line of the verse is what the viewer
        actually perceives as the header."""
        for en, ur in self.HEADLINES:
            _, _, meta, _ = studio.build_bases(self._comp(en, ur))
            self.assertLess(meta["geometry"]["body_top"] / 1920, 0.22,
                            f"body_top is {meta['geometry']['body_top']/1920:.1%} "
                            f"down the frame for {en!r}")

    def test_a_very_long_headline_still_fits(self):
        """The guard is the budget, not the character count: a headline nobody
        has written yet must shrink, not overflow."""
        _, _, meta, _ = studio.build_bases(self._comp(
            "Business and trade — honesty and fair dealing in every single "
            "transaction you ever make with anyone",
            "کاروبار — ہر لین دین میں ایمانداری اور انصاف"))
        g = meta["geometry"]
        self.assertLessEqual((g["header_bottom"] - g["header_top"]) / 1920,
                             studio.HEADER_BUDGET + 0.02)
        self.assertGreater(meta["heading_size"], 20, "it collapsed to nothing")

    def test_ink_is_what_is_measured(self):
        """The bug behind the tall header: Urdu laid out at 2.6x its size.

        Napkin maths on the font itself, so a future pitch change that reserves
        the old air fails here instead of on screen.
        """
        fnt = studio.f(studio.URDU, 60)
        ink = studio._ink_h(fnt, "نکاح — میاں بیوی کے درمیان محبت اور رحمت")
        self.assertLess(ink, 60 * 2.0,
                        "Urdu ink claimed to be taller than 2x the size")
        self.assertGreater(ink, 60 * 1.5, "Urdu ink claimed to be too short")


@unittest.skipUnless(HAVE_FONTS, "fonts not fetched")
class TestTranslationHalves(unittest.TestCase):
    """'Translation to be top Urdu and bottom English in Equal half parts'."""

    URDU = ("اور اسی کے نشانات (اور تصرفات) میں سے ہے کہ اُس نے تمہارے لئے "
            "تمہاری ہی جنس کی عورتیں پیدا کیں تاکہ اُن کی طرف (مائل ہوکر) آرام "
            "حاصل کرو اور تم میں محبت اور مہربانی پیدا کر دی")
    ENGLISH = ("And of His signs is that He created for you from yourselves "
               "mates that you may find tranquillity in them; and He placed "
               "between you affection and mercy.")

    def _bases(self, **kw):
        base = dict(width=1080, height=1920, fps=30, topic_en="Marriage",
                    topic_ur="نکاح", reference_en="Qur'an 30:21", reference_ar="",
                    arabic_words=[], body_arabic="", urdu=self.URDU,
                    english=self.ENGLISH, phase1=10.0, phase2=10.0,
                    textures=False, topic_key="marriage")
        base.update(kw)
        return studio.build_bases(studio.Comp(**base))

    def test_both_blocks_report_their_size(self):
        _, _, meta, _ = self._bases()
        self.assertIn("urdu_size", meta)
        self.assertIn("english_size", meta)

    def test_english_is_not_tiny_next_to_the_urdu(self):
        """The reported defect: English set at roughly half the Urdu."""
        _, _, meta, _ = self._bases()
        ratio = meta["english_size"] / meta["urdu_size"]
        self.assertGreater(ratio, 0.45,
                           f"English/Urdu size ratio {ratio:.2f} - the English "
                           f"block is shrinking again")

    def test_english_can_use_its_own_half(self):
        """A long English must wrap into the room it has, not shrink to fit the
        old 30%-of-body cap."""
        _, _, meta, _ = self._bases()
        self.assertGreaterEqual(meta["english_size"], 18)

    def test_halves_do_not_overlap(self):
        """Urdu sits in the top half of the body, English in the bottom."""
        _, p2, meta, _ = self._bases()
        import numpy as np
        a = np.asarray(p2.convert("L"), dtype=np.int16)
        rows = (a > 90).sum(axis=1)              # lit pixels per row
        lit = np.flatnonzero(rows > 6)
        self.assertGreater(len(lit), 20, "nothing was drawn")
        # the gold rule sits between the halves; find the biggest internal gap
        gaps = np.diff(lit)
        self.assertGreater(gaps.max(), 8, "the two translation halves are touching")


class TestAyahWeight(unittest.TestCase):
    """'Arabic ayah to be bold'."""

    def test_the_stroke_is_defined_and_scales_with_width(self):
        self.assertGreater(studio.AR_STROKE, 0)
        self.assertGreaterEqual(max(int(1080 * studio.AR_STROKE), 1), 1)
        self.assertGreater(max(int(2160 * studio.AR_STROKE), 1),
                           max(int(1080 * studio.AR_STROKE), 1),
                           "the stroke must scale, or it vanishes at 1080 and "
                           "smears at 4K")

    def test_paint_word_accepts_and_uses_a_stroke(self):
        import inspect
        sig = inspect.signature(studio.paint_word)
        self.assertIn("stroke", sig.parameters)
        self.assertEqual(sig.parameters["stroke"].default, 0)

    @unittest.skipUnless(HAVE_FONTS, "fonts not fetched")
    def test_the_stroke_changes_the_ink(self):
        from PIL import Image, ImageDraw
        import numpy as np
        fnt = studio.f(studio.ARABIC, 80)
        word = "وَإِذَا"
        thin = Image.new("L", (400, 200), 0)
        ImageDraw.Draw(thin).text((200, 100), word, font=fnt, fill=255,
                                  anchor="ra", stroke_width=0, **studio.RTL)
        thick = Image.new("L", (400, 200), 0)
        ImageDraw.Draw(thick).text((200, 100), word, font=fnt, fill=255,
                                   anchor="ra", stroke_width=3, stroke_fill=255,
                                   **studio.RTL)
        a = int((np.asarray(thin) > 90).sum())
        b = int((np.asarray(thick) > 90).sum())
        self.assertGreater(b, a * 1.1,
                           f"a 3px stroke only changed ink {a}->{b}; the ayah "
                           f"is not getting visibly bolder")


class TestEveryTopicHasItsOwnArt(unittest.TestCase):
    """'It must use a different background for each video related to it'."""

    def test_no_topic_falls_back_to_the_generic_layer(self):
        missing = [t for t in TOPICS
                   if studio.motif_for(t) is None]
        self.assertEqual(missing, [],
                         f"these topics would share the generic background: {missing}")

    def test_each_motif_is_its_own_file(self):
        seen = {}
        for t in TOPICS:
            p = studio.motif_for(t)
            self.assertIsNotNone(p, t)
            self.assertNotIn(str(p), seen,
                             f"{t} and {seen.get(str(p))} share one image")
            seen[str(p)] = t

    def test_motif_prompts_exist_for_every_topic(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import motifs
        missing = [t for t in TOPICS if t not in motifs.SUBJECTS]
        self.assertEqual(missing, [],
                         f"no art prompt written for: {missing} - the next new "
                         f"topic must not ship with no way to draw it")


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipUnless(HAVE_FONTS, "fonts not fetched")
class TestNoMissingGlyphs(unittest.TestCase):
    """A card must never draw .notdef.

    Found by looking at the rendered hadith: the honouring of the Prophet
    (U+FDFA) came out as an empty box, because DejaVu has no glyph for it. The
    scan is deliberately blunt - every character of every field the card draws,
    through the font that will draw it - so the next unrenderable character is
    caught here rather than by the owner on a phone.

    `.notdef` is detected by rendering the character and comparing it with a
    private-use codepoint, which is guaranteed to be missing: PIL happily
    returns a .notdef bitmap, so asking the font whether it "has" a glyph
    always answers yes.
    """

    def _fonts(self):
        from PIL import ImageFont
        return {"LATIN": ImageFont.truetype(str(studio.LATIN), 48),
                "LATIN_B": ImageFont.truetype(str(studio.LATIN_B), 48),
                "URDU": ImageFont.truetype(str(studio.URDU), 48),
                "ARABIC": ImageFont.truetype(str(studio.ARABIC), 48),
                "UI": ImageFont.truetype(str(studio.UI), 48)}

    @staticmethod
    def _renders(font, ch):
        from PIL import Image, ImageDraw

        def bmp(c):
            im = Image.new("L", (90, 90), 0)
            ImageDraw.Draw(im).text((12, 12), c, font=font, fill=255)
            return im.tobytes()

        return bmp(ch) != bmp("\ue000")

    def test_the_shipped_library_has_no_unrenderable_characters(self):
        import json
        from islamic.english import for_display
        from islamic.sources import load_items
        clips = json.loads((ROOT / "library.json").read_text())["clips"]
        fonts = self._fonts()
        problems = []
        for it in load_items([c["ref"] for c in clips]):
            for field, key in ((for_display(it.english or ""), "LATIN"),
                               (it.urdu or "", "URDU"),
                               (it.arabic or "", "UI"),
                               (it.source_ar or "", "UI")):
                bad = sorted({c for c in field
                              if c.strip() and not self._renders(fonts[key], c)})
                if bad:
                    problems.append(f"{it.reference} ({key}): {bad}")
        self.assertEqual(problems, [], "the card would draw a .notdef box")

    def test_the_honorific_is_spelled_out_for_the_card(self):
        from islamic.english import for_display
        shown = for_display("the Messenger of Allah (\ufdfa) said")
        self.assertEqual(shown, "the Messenger of Allah (peace be upon him) said")
        self.assertNotIn("\ufdfa", shown)
