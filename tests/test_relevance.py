#!/usr/bin/env python3
"""
Tests for the two things that go wrong quietly: a topic that the verse does not
support, and Urdu text that reaches the voice engine misspelled.

Every test here is stdlib-only and runs offline. The scripts are imported
directly so the tests exercise the code that actually runs, not a copy.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic import relevance                                   # noqa: E402
from islamic.relevance import check, text_from_record           # noqa: E402
from islamic.topics import TOPICS                               # noqa: E402
from islamic.urdu import normalize_for_speech, number_to_urdu, words  # noqa: E402
from tools import plan_render                                   # noqa: E402


class TestTheReviewedPairing(unittest.TestCase):
    """The finding that created this gate, kept as a test forever."""

    BODY_81_8 = "اور جب لڑکی سے جو زندہ دفنا دی گئی ہو پوچھا جائے گا"

    def test_daughters_no_longer_accepts_81_8(self):
        r = check("daughters", self.BODY_81_8)
        self.assertFalse(r.ok, "81:8 must never again be labelled 'Daughters'")
        self.assertIn("worth", r.missing)
        self.assertIn("does not survive", r.reason)

    def test_81_8_is_carried_by_justice(self):
        r = check("justice", self.BODY_81_8)
        self.assertTrue(r.ok, r.reason)
        self.assertEqual(set(r.matched), {"wronged", "accounted"})

    def test_a_shared_noun_is_not_a_relation(self):
        """The exact reasoning error: 'girl' appears, so it must be about daughters."""
        self.assertIn("لڑکی", "".join(TOPICS["daughters"]["claims"]["daughters"]))
        self.assertFalse(check("daughters", self.BODY_81_8).ok,
                         "sharing a noun must not be enough")

    def test_daughters_topic_still_works_for_what_it_claims(self):
        body = ("جسے چاہتا ہے بیٹیاں عطا کرتا ہے اور جسے چاہتا ہے بیٹے بخشتا ہے")
        self.assertTrue(check("daughters", body).ok)


class TestClaimDeclarations(unittest.TestCase):

    def test_every_required_claim_has_a_word_list(self):
        for key, spec in TOPICS.items():
            for req in spec.get("requires", []):
                self.assertIn(req, spec.get("claims", {}),
                              f"topic '{key}' requires '{req}' but declares no words for it")

    def test_requires_is_never_empty(self):
        for key, spec in TOPICS.items():
            self.assertTrue(spec.get("requires"),
                            f"topic '{key}' has no requires - it would accept any text")

    def test_claims_are_urdu(self):
        for key, spec in TOPICS.items():
            for claim, forms in spec.get("claims", {}).items():
                self.assertTrue(forms, f"{key}.{claim} is empty")
                for f in forms:
                    self.assertTrue(any("\u0600" <= c <= "\u06ff" for c in f),
                                    f"{key}.{claim}: {f!r} is not Urdu script")

    def test_unknown_topic_is_refused(self):
        r = check("no-such-topic", "کچھ")
        self.assertFalse(r.ok)
        self.assertIn("unknown topic", r.reason)


class TestSpellingFolding(unittest.TestCase):
    """Publishers mix Arabic and Urdu codepoints for the same letter."""

    def test_alef_maddah_precomposed_and_decomposed_match(self):
        pre = "جہنم سے آڑ"                     # آ = U+0622
        dec = "جہنم سے ا\u0653ڑ"               # ا + U+0653 maddah
        self.assertNotEqual(pre, dec, "the fixture must actually differ")
        self.assertTrue(check("daughters", "بیٹیاں ہیں اور " + pre).ok)
        self.assertTrue(check("daughters", "بیٹیاں ہیں اور " + dec).ok,
                        "decomposed alef-maddah must fold like the precomposed one")

    def test_arabic_kaf_folds_to_urdu_kaf(self):
        self.assertEqual(relevance.strip_marks("كہانی"), relevance.strip_marks("کہانی"))

    def test_arabic_yeh_folds_to_urdu_yeh(self):
        self.assertEqual(relevance.strip_marks("بيٹياں"), relevance.strip_marks("بیٹیاں"))

    def test_teh_marbuta_folds_to_urdu_heh(self):
        self.assertEqual(relevance.strip_marks("ة"), relevance.strip_marks("ہ"))

    def test_harakat_are_ignored(self):
        self.assertEqual(relevance.strip_marks("حَمْد"), relevance.strip_marks("حمد"))


class TestUrduForSpeech(unittest.TestCase):

    def test_footnote_marker_never_becomes_a_spoken_number(self):
        """'۱؎' after digits would otherwise be read as the word 'one'."""
        out = normalize_for_speech("سور کے گلے میں جواہر ۱؎۔")
        self.assertNotIn("ایک", out, "a footnote became a spoken number")
        self.assertNotIn("\u060e", out)
        self.assertTrue(out.endswith("۔") or out.endswith("جواہر"))

    def test_bracketed_aside_becomes_a_pause_not_a_deletion(self):
        out = normalize_for_speech("اس کے نشانات (اور تصرفات) میں سے")
        self.assertNotIn("(", out)
        self.assertNotIn(")", out)
        self.assertIn("اور تصرفات", out, "the translator's aside must survive")
        self.assertIn("،", out)

    def test_digits_become_words(self):
        out = normalize_for_speech("اس نے 500 روپے دیے")
        self.assertNotIn("500", out)
        self.assertIn("پانچ سو", out)

    def test_urdu_digits_become_words(self):
        self.assertIn("اکیس", normalize_for_speech("عمر ۲۱ سال"))

    def test_ascii_punctuation_becomes_urdu(self):
        out = normalize_for_speech("علم فرض ہے, اور عمل بھی.")
        self.assertIn("،", out)
        self.assertIn("۔", out)
        self.assertNotIn(".", out)

    def test_honorific_symbol_is_spelled_out(self):
        self.assertIn("صلی اللہ علیہ وسلم", normalize_for_speech("رسول اللہ \ufdfa نے فرمایا"))

    def test_roman_letters_are_removed(self):
        self.assertNotIn("k", normalize_for_speech("علم k فرض"))

    def test_normalising_twice_changes_nothing(self):
        src = "یہ ۱؎ (نوٹ) ہے، اور 42 بار۔"
        once = normalize_for_speech(src)
        self.assertEqual(once, normalize_for_speech(once))

    def test_our_own_published_copy_normalises(self):
        """The real hadith body carries a footnote marker we must not voice."""
        body = text_from_record("ibnmajah-224")
        self.assertIsNotNone(body, "build record missing")
        out = normalize_for_speech(body)
        self.assertNotIn("\u060e", out)
        self.assertNotIn("۱؎", out)


class TestNumberTable(unittest.TestCase):

    def test_covers_zero_to_one_hundred(self):
        for n in range(101):
            self.assertTrue(number_to_urdu(n).strip(), f"no word for {n}")

    def test_no_duplicate_spellings_in_range(self):
        """A duplicated word means two numbers read identically - a real defect."""
        seen: dict[str, int] = {}
        for n in range(100):
            w = number_to_urdu(n)
            self.assertNotIn(w, seen, f"{n} and {seen.get(w)} both read {w!r}")
            seen[w] = n

    def test_hundreds_and_scales(self):
        self.assertEqual(number_to_urdu(100), "سو")
        self.assertEqual(number_to_urdu(500), "پانچ سو")
        self.assertEqual(number_to_urdu(121), "سو اکیس")
        self.assertIn("ہزار", number_to_urdu(2500))
        self.assertIn("لاکھ", number_to_urdu(100_000))

    def test_negative_is_signed_not_silent(self):
        self.assertTrue(number_to_urdu(-3).startswith("منفی"))


class TestWordCounting(unittest.TestCase):

    def test_only_tokens_with_a_letter_count(self):
        self.assertEqual(words("١٢ ۚ ۖ بسم"), ["بسم"])

    def test_matches_the_video_gate(self):
        """Two counters that disagree would put the timing check in dispute."""
        from tools.check_video import count_words
        samples = ["وَإِذَا ٱلْمَوْءُۥدَةُ سُئِلَتْ", "بسم الله الرحمن الرحيم",
                   "٢١", "ہر مسلمان پر فرض ہے"]
        for s in samples:
            self.assertEqual(len(words(s)), count_words(s), f"disagreement on {s!r}")

    def test_real_uthmani_verse_counts_words_not_marks(self):
        self.assertEqual(len(words("بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ ٢١")), 4)


class TestThePlanRefusesBadPairings(unittest.TestCase):

    def _library(self, topic: str) -> Path:
        d = Path(tempfile.mkdtemp())
        d.mkdir(parents=True, exist_ok=True)
        (d / "library.json").write_text(json.dumps({"clips": [
            {"slug": "quran-81-8", "ref": "quran:81:8", "topic": topic}]}),
            encoding="utf-8")
        return d / "library.json"

    def test_plan_refuses_daughters_81_8(self):
        with self.assertRaises(SystemExit) as cm:
            plan_render.load_library(self._library("daughters"), offline=True)
        self.assertIn("REFUSED", str(cm.exception))

    def test_plan_allows_justice_81_8(self):
        clips = plan_render.load_library(self._library("justice"), offline=True)
        self.assertEqual(clips[0]["topic"], "justice")

    def test_the_check_can_be_switched_off_deliberately(self):
        clips = plan_render.load_library(self._library("daughters"), relevance=False)
        self.assertEqual(len(clips), 1)

    def test_the_shipped_library_is_clean(self):
        clips = plan_render.load_library(offline=True)
        self.assertGreaterEqual(len(clips), 3)
        for c in clips:
            body = text_from_record(c["slug"])
            self.assertIsNotNone(body, f"{c['slug']} has no build record to audit")
            self.assertTrue(check(c["topic"], body).ok, c["slug"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
