"""The authenticity gate, tested offline on the gradings that taught it.

Network-free on purpose: CI runs these before any render, and a gate whose
tests need the network would be skipped exactly when the network is flaky.
The gradings below are copied from the hadith-api payloads as fetched on
2026-10-11 - they are grader verdicts (metadata), not hadith text.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic.verify import classify, judge, skeleton  # noqa: E402

IBNMAJAH_224 = [  # the clip we published, and withdrew
    {"name": "Al-Albani", "grade": "Very Daif"},
    {"name": "Muhammad Fouad Abd al-Baqi", "grade": "Very Daif"},
    {"name": "Shuaib Al Arnaut", "grade": "Very Daif"},
    {"name": "Zubair Ali Zai", "grade": "Daif"},
]
TIRMIDHI_1916 = [  # disputed
    {"name": "Ahmad Muhammad Shakir", "grade": "Daif"},
    {"name": "Al-Albani", "grade": "Daif"},
    {"name": "Bashar Awad Maarouf", "grade": "Hasan"},
    {"name": "Zubair Ali Zai", "grade": "Hasan"},
]
TIRMIDHI_2646 = [  # its replacement
    {"name": "Ahmad Muhammad Shakir", "grade": "Sahih"},
    {"name": "Al-Albani", "grade": "Sahih"},
    {"name": "Zubair Ali Zai", "grade": "Sahih Muslim"},
]
ABUDAWUD_1 = [
    {"name": "Al-Albani", "grade": "Hasan Sahih"},
    {"name": "Shuaib Al Arnaut", "grade": "Sahih Lighairihi"},
    {"name": "Zubair Ali Zai", "grade": "Isnaad Hasan"},
]


class TestTheHadithPolicy(unittest.TestCase):
    def test_the_published_weak_hadith_is_refused(self):
        ok, line, why = judge("ibnmajah", IBNMAJAH_224)
        self.assertFalse(ok, "ibnmajah:224 is Very Da'if and went out once already")
        self.assertEqual(line, "")
        self.assertTrue(any("weak" in w for w in why))

    def test_a_disputed_hadith_is_refused_not_averaged(self):
        ok, _, why = judge("tirmidhi", TIRMIDHI_1916)
        self.assertFalse(ok, "two graders say da'if: that is a refusal, "
                             "however many say hasan")

    def test_a_unanimously_sahih_hadith_passes_and_names_its_graders(self):
        ok, line, why = judge("tirmidhi", TIRMIDHI_2646)
        self.assertTrue(ok, why)
        self.assertTrue(line.startswith("Sahih"))
        self.assertIn("Al-Albani", line)

    def test_hasan_wordings_are_accepted(self):
        ok, line, why = judge("abudawud", ABUDAWUD_1)
        self.assertTrue(ok, why)

    def test_bukhari_and_muslim_pass_without_per_hadith_grades(self):
        for c in ("bukhari", "muslim"):
            ok, line, _ = judge(c, [])
            self.assertTrue(ok)
            self.assertTrue(line.startswith("Sahih"))

    def test_no_grades_outside_the_two_sahihs_is_a_refusal(self):
        for c in ("ibnmajah", "tirmidhi", "nawawi", "qudsi"):
            ok, _, _ = judge(c, [])
            self.assertFalse(ok, f"{c} with no grading must not pass")

    def test_an_unrecognised_grade_wording_stops_the_line(self):
        ok, _, why = judge("tirmidhi", [{"name": "X", "grade": "Sahih"},
                                         {"name": "Y", "grade": "Gharib"}])
        self.assertFalse(ok)
        self.assertTrue(any("unrecognised" in w for w in why))

    def test_weak_words_win_over_the_strong_word_inside_them(self):
        # "Sahih" must not be found inside a weak verdict and counted as strong
        for g in ("Very Daif", "Isnaad Daif", "Da'if", "Maudu", "Munkar",
                  "Daif Jiddan", "Mawdu'", "Shadh"):
            self.assertEqual(classify(g), "weak", g)
        for g in ("Sahih", "Hasan", "Hasan Sahih", "Sahih Lighairihi",
                  "Isnaad Hasan", "Sahih - Bukhari And Muslim"):
            self.assertEqual(classify(g), "strong", g)


class TestTheQuranSkeleton(unittest.TestCase):
    """Synthetic Arabic words only - no verse text is stored in the tests."""

    def test_orthographic_conventions_are_not_differences(self):
        # tatweel, harakat, small alef and alef forms differ between Uthmani
        # editions; the letters do not
        self.assertEqual(skeleton("كِتَـٰبٌ"), skeleton("كِتَٰبٌ"))
        self.assertEqual(skeleton("ٱلْكِتَابُ"), skeleton("الكتاب"))

    def test_a_changed_letter_is_a_difference(self):
        self.assertNotEqual(skeleton("كَتَبَ"), skeleton("كَتَمَ"))
        self.assertNotEqual(skeleton("لَكُمْ"), skeleton("لَهُمْ"))

    def test_a_dropped_letter_is_a_difference(self):
        self.assertNotEqual(skeleton("رَحْمَةً"), skeleton("رَحْمَ"))


if __name__ == "__main__":
    unittest.main()
