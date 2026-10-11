#!/usr/bin/env python3
"""
Regression suite for the gates that protect publication.

These tests exist because of something that actually happened: `check_video.py`
was written, and its first run against a real clip reported a problem that turned
out to be a bug in the *test*, not in the renderer — the ayah text is 21
whitespace tokens because the Uthmani edition separates waqf marks. A gate that
cries wolf is worse than no gate, so the counting rule is pinned here, along with
every promise the gate is supposed to defend.

Run either way:

    python3 -m unittest discover -s tests -v
    python3 tests/test_gates.py

No dependencies beyond the standard library, so it runs unchanged on a GitHub
runner, in this sandbox, and on a laptop.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.check_video import count_words, correctness_failures  # noqa: E402
from tools import plan_render  # noqa: E402
from tools import publish as publish_mod  # noqa: E402


# ---------------------------------------------------------------------------
# the counting rule
# ---------------------------------------------------------------------------

class TestCountWords(unittest.TestCase):
    """Words are tokens containing a letter; punctuation and numerals are not."""

    def test_plain_words(self):
        self.assertEqual(count_words("وَمِنْ ءَايَٰتِهِۦٓ أَنْ خَلَقَ"), 4)

    def test_waqf_mark_is_not_a_word(self):
        # ۚ is a pause mark. Counting it as a word is the bug that sent the first
        # revision of the gate after a renderer that was correct.
        self.assertEqual(count_words("وَرَحْمَةً ۚ إِنَّ"), 2)

    def test_a_real_excerpt_with_waqf_marks(self):
        # Drawn from 2:275. The property under test is the one that caused the
        # bug: whitespace tokens overcount because the edition separates waqf
        # marks, and a naive count makes the gate accuse a correct renderer.
        text = "فَمَن جَآءَهُۥ مَوْعِظَةٌ مِّن رَّبِّهِۦ فَٱنتَهَىٰ ۖ وَأَمْرُهُۥٓ إِلَى ٱللَّهِ ۖ"
        self.assertEqual(count_words(text), 9)
        self.assertEqual(len(text.split()), 11)
        self.assertLess(count_words(text), len(text.split()))

    def test_verse_number_is_not_a_word(self):
        self.assertEqual(count_words("٢١"), 0)
        self.assertEqual(count_words("21"), 0)

    def test_empty_and_whitespace(self):
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("   \n  "), 0)

# ---------------------------------------------------------------------------
# the promises
# ---------------------------------------------------------------------------

def _quran_build(**over) -> dict:
    b = {
        "reference": "quran:30:21",
        "source": "Qur'an 30:21 · Ar-Room",
        "kind": "quran",
        "reciter": "Mishary Rashid Alafasy",
        "timings_source": "api.quran.com v4 audio.segments",
        # 8 words. Kept honest by test_fixture_counts_its_own_words below.
        "arabic": "وَمِنْ ءَايَٰتِهِۦٓ أَنْ خَلَقَ لَكُم مِّنْ أَنفُسِكُمْ أَزْوَٰجًۭا",
        "word_count": 8,
        "seconds": 52.61,
    }
    b.update(over)
    return b


def _hadith_build(**over) -> dict:
    b = {
        "reference": "ibnmajah:224",
        "source": "Sunan Ibn Majah, Hadith 224",
        "kind": "hadith",
        "grade": "See a scholar — this collection contains a range of grades",
        "arabic": "طَلَبُ الْعِلْمِ فَرِيضَةٌ عَلَى كُلِّ مُسْلِمٍ",
        "word_count": 0,
        "seconds": 47.64,
    }
    b.update(over)
    return b


class TestPromises(unittest.TestCase):
    """Each test is one promise the project makes. None of them may be dropped."""

    def assert_blocked(self, build, needle):
        fails = correctness_failures(build)
        self.assertTrue(fails, f"expected a failure for {needle}")
        self.assertTrue(any(needle in f for f in fails),
                        f"expected a reason mentioning {needle!r}, got {fails}")

    def test_a_good_quran_clip_passes(self):
        self.assertEqual(correctness_failures(_quran_build()), [])

    def test_a_good_hadith_clip_passes(self):
        self.assertEqual(correctness_failures(_hadith_build()), [])

    def test_no_build_record_is_a_failure(self):
        # Unverifiable is not the same as fine.
        self.assert_blocked({}, "no build record")

    def test_citation_required(self):
        self.assert_blocked(_quran_build(source=""), "human-readable source")
        self.assert_blocked(_quran_build(reference=""), "no reference")

    def test_quran_must_name_its_reciter(self):
        # The fingerprint of the TTS fallback having fired. Qur'an audio is a real
        # recitation, always; this is the promise the whole project rests on.
        self.assert_blocked(_quran_build(reciter=""), "names no reciter")

    def test_quran_must_record_where_timings_came_from(self):
        self.assert_blocked(_quran_build(timings_source=""), "timings_source")

    def test_untrusted_collection_rejected(self):
        self.assert_blocked(_quran_build(reference="someblog:7"), "TRUSTED_COLLECTIONS")

    def test_hadith_must_carry_a_grade(self):
        self.assert_blocked(_hadith_build(grade=""), "grade line")

    def test_scripture_must_actually_be_present(self):
        self.assert_blocked(_quran_build(arabic=""), "no Arabic text")
        self.assert_blocked(_hadith_build(arabic=""), "no Arabic text")

    def test_fixture_counts_its_own_words(self):
        # Guards the fixture, so a wrong expectation here cannot quietly turn
        # into a passing test of nothing.
        self.assertEqual(count_words(_quran_build()["arabic"]), 8)

    def test_dropped_word_is_caught(self):
        # word_count comes from the recitation's own segment list, the text from
        # another publisher. Agreement means no word can be silently missing.
        self.assert_blocked(_quran_build(word_count=7), "would drop 1")
        self.assert_blocked(_quran_build(word_count=9), "for a different text")


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------

class TestPlan(unittest.TestCase):

    def test_library_is_valid(self):
        clips = plan_render.load_library()
        self.assertGreater(len(clips), 0)
        for c in clips:
            self.assertEqual(c["slug"], c["ref"].replace(":", "-"))

    def test_require_audio_is_derived_from_the_reference(self):
        by_slug = {c["slug"]: c for c in plan_render.load_library()}
        self.assertTrue(by_slug["quran-30-21"]["require_audio"])
        # the hadith in the library (ibnmajah-224 until it was withdrawn as
        # Very Da'if) is a silent-recitation card
        self.assertFalse(by_slug["tirmidhi-2646"]["require_audio"])

    def test_slug_ref_mismatch_is_refused(self):
        # A slug that does not match its reference is how a video ends up filed
        # under the wrong citation on the site.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "library.json"
            p.write_text(json.dumps({"clips": [
                {"slug": "quran-30--21", "ref": "quran:30:21", "topic": "marriage"}]}))
            with self.assertRaises(SystemExit):
                plan_render.load_library(p)

    def test_unknown_topic_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "library.json"
            p.write_text(json.dumps({"clips": [
                {"slug": "quran-30-21", "ref": "quran:30:21", "topic": "not-a-topic"}]}))
            with self.assertRaises(SystemExit):
                plan_render.load_library(p)

    def test_duplicate_slug_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "library.json"
            one = {"slug": "quran-30-21", "ref": "quran:30:21", "topic": "marriage"}
            p.write_text(json.dumps({"clips": [one, dict(one)]}))
            with self.assertRaises(SystemExit):
                plan_render.load_library(p)

    def test_selection_by_slug_and_by_ref(self):
        clips = plan_render.load_library()
        self.assertEqual(len(plan_render.select(clips, "quran-30-21")), 1)
        self.assertEqual(len(plan_render.select(clips, "quran:30:21")), 1)
        self.assertEqual(len(plan_render.select(clips, "")), len(clips))
        with self.assertRaises(SystemExit):
            plan_render.select(clips, "does-not-exist")

    def test_github_output_values_are_single_line(self):
        # A newline in an output value silently truncates $GITHUB_OUTPUT, and the
        # matrix would then be built from half a JSON document.
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "plan_render.py"),
                              "--github-output"], capture_output=True, text=True).stdout
        values = dict(l.split("=", 1) for l in out.strip().splitlines())
        for k, v in values.items():
            self.assertNotIn("\n", v, f"{k} is not single-line")
        self.assertEqual(len(json.loads(values["clips"])), 3)


# ---------------------------------------------------------------------------
# the gate, end to end, on a real file
# ---------------------------------------------------------------------------

class TestGateOnRealClip(unittest.TestCase):
    """Uses a published clip if one is present. Cheap, so it always runs in CI."""

    @classmethod
    def setUpClass(cls):
        cls.clips = sorted((ROOT / "web" / "video").glob("*.mp4"))
        if not cls.clips:
            raise unittest.SkipTest("no published clips to check")

    def _run(self, video: Path):
        bj = ROOT / "output" / "video" / (video.stem + ".build.json")
        cmd = [sys.executable, str(ROOT / "tools" / "check_video.py"), str(video)]
        if bj.exists():
            cmd += ["--build-json", str(bj)]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_published_clips_pass_their_own_gate(self):
        for v in self.clips:
            with self.subTest(clip=v.name):
                p = self._run(v)
                self.assertEqual(p.returncode, 0,
                                 f"{v.name} fails its gate:\n{p.stderr}")

    def _quran_clip(self):
        for v in self.clips:
            bj = ROOT / "output" / "video" / (v.stem + ".build.json")
            if not bj.exists():
                continue
            build = json.loads(bj.read_text(encoding="utf-8"))
            if build.get("kind") == "quran":
                return v, bj, build
        return None, None, None

    def test_gate_blocks_a_tampered_build_record(self):
        v, bj, build = self._quran_clip()
        if v is None:
            self.skipTest("no Qur'an clip with a build record published yet")
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / bj.name
            bad.write_text(json.dumps({**build, "reciter": ""}), encoding="utf-8")
            p = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "check_video.py"), str(v),
                 "--build-json", str(bad)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, "a Qur'an clip with no reciter passed")
            self.assertIn("reciter", p.stderr)


# ---------------------------------------------------------------------------
# publishing must not be able to destroy the library
# ---------------------------------------------------------------------------

class TestPublishIsNonDestructive(unittest.TestCase):
    """A subset render must never prune the rest of the site."""

    def test_manifest_is_a_superset_of_what_was_built(self):
        manifest = ROOT / "web" / "video" / "manifest.json"
        if not manifest.exists():
            self.skipTest("nothing published yet")
        items = json.loads(manifest.read_text(encoding="utf-8"))["items"]
        self.assertTrue(items)
        for i in items:
            # Media is not in git any more (it lives in a GitHub Release), so
            # "the mp4 exists in the checkout" is the wrong thing to require -
            # it was only ever true on a laptop that had just rendered. What
            # must be true everywhere: the citation is in git, and the item
            # names the Release its media can be fetched from.
            rec = ROOT / "web" / "video" / i["file"].replace(".mp4", ".build.json")
            self.assertTrue(rec.exists(), f"no citation in git for {i['file']}")
            self.assertTrue(i.get("release"),
                            f"{i['file']} names no Release - Pages could not serve it")
            self.assertIn("poster", i)

    def test_no_media_is_tracked_by_git(self):
        """The rule that ended the history rewrites. Checked on the index."""
        import subprocess
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                             text=True).stdout.split("\n")
        media = [f for f in out if f.lower().endswith((".mp4", ".mp3", ".wav", ".m4a"))
                 or f.startswith("web/video/posters/")]
        self.assertEqual(media, [], f"media committed to git: {media}")

    def test_subset_publish_keeps_the_others(self):
        # Everything published is also present as a built artefact, so a subset
        # publish should find one clip to build and carry the rest forward.
        web = ROOT / "web" / "video"
        built = list((ROOT / "output" / "video").glob("*.mp4"))
        if not built or not (web / "manifest.json").exists():
            self.skipTest("no built clips to try")
        before = json.loads((web / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            one = built[0]
            for suffix in (".mp4", ".build.json"):
                src = one.with_suffix(suffix)
                if src.exists():
                    (Path(d) / src.name).write_bytes(src.read_bytes())
            items, held = publish_mod.collect([d])
            self.assertEqual(held, [], f"a published clip failed its gate: {held}")
            self.assertEqual([i["file"] for i in items], [one.name])
        # And the site still lists everything it listed before.
        after = json.loads((web / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(after["count"], before["count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
