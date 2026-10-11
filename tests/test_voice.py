#!/usr/bin/env python3
"""
Tests for the narration voice, the flow reading, and the instrument used to
measure both.

Nothing here loads a model or opens a socket: the flow behaviour is tested
through the functions that decide it, and the metrics instrument is tested
against synthetic audio whose answer is known by construction.
"""

from __future__ import annotations

import inspect
import sys
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from islamic import english, urdu                                  # noqa: E402
from islamic.voice import (VOICES, UrduVoice, default_voice,       # noqa: E402
                           _chunk_ends_sentence, _ends_sentence, _tail_silence)
from tools.voice_metrics import analyse, pauses                    # noqa: E402


class TestVoiceCatalogue(unittest.TestCase):

    def test_every_voice_declares_a_language_and_a_licence(self):
        for key, spec in VOICES.items():
            self.assertTrue(spec.get("lang"), f"{key} has no language")
            self.assertTrue(spec.get("licence"), f"{key} has no licence")
            self.assertTrue(spec.get("rel"), f"{key} has no model path")

    def test_urdu_and_english_defaults(self):
        self.assertEqual(default_voice("ur"), "fasih")
        self.assertEqual(VOICES[default_voice("ur")]["lang"], "ur")
        self.assertEqual(VOICES[default_voice("en")]["lang"], "en")

    def test_the_default_english_voice_is_one_we_could_publish(self):
        """English is now the DEFAULT narration language ('TTS will be in
        English'), so the default voice has to be licence-clean. It was lessac,
        which is a Blizzard research licence - fine for an A/B, not for the
        channel. The prettier voice stays available explicitly.
        """
        self.assertFalse(VOICES[default_voice("en")].get("test_only", False),
                         f"the English default is {default_voice('en')}, which is "
                         f"flagged test_only - a published clip would ship it")
        self.assertTrue(VOICES["en"]["test_only"],
                        "lessac should stay available as the A/B voice")

    def test_the_research_licensed_voice_is_marked_test_only(self):
        """It sounds good and its licence is a Blizzard research licence.
        If this flag is ever dropped, a published clip can ship it."""
        self.assertTrue(VOICES["en"]["test_only"])
        self.assertFalse(VOICES.get("en_free", {}).get("test_only", False))

    def test_the_voice_reads_english_by_default(self):
        """'TTS will be in English, not in Urdu. Translation will be in Urdu and
        English both while TTS will read English.'

        Pinned at the CLI, because this is the flag a re-render forgets.
        """
        from islamic.produce import build_parser
        d = build_parser().parse_args([])
        self.assertEqual(d.narrate, "english",
                         "the narration language defaulted back to Urdu")
        self.assertTrue(d.english,
                        "the card must carry both translations by default")
        self.assertFalse(build_parser().parse_args(["--no-english"]).english,
                         "--no-english no longer turns the caption off")
        self.assertEqual(build_parser().parse_args(["--narrate", "urdu"]).narrate,
                         "urdu", "Urdu narration must stay reachable")

    def test_the_narrator_script_follows_the_language(self):
        """English narration reads the ENGLISH translation, not the Urdu."""
        self.assertIn("peace be upon him",
                      english.normalize_for_speech_en(
                          "The Messenger of Allah (\ufdfa) said: seek knowledge."),
                      "an honorific ligature would be read as nothing, or worse, "
                      "as garbage - it is spoken in full")
        self.assertNotIn("\ufdfa", english.normalize_for_speech_en(
            "The Messenger of Allah (\ufdfa) said: seek knowledge."))

    def test_the_shippable_english_voice_is_cc_by(self):
        self.assertIn("CC-BY", VOICES["en_free"]["licence"])

    def test_english_voices_declare_a_slower_pace(self):
        """Measured: the model default runs 227-245 wpm; creators median 184.5."""
        for key, spec in VOICES.items():
            if spec["lang"] == "en":
                ls = spec.get("length_scale")
                self.assertIsNotNone(ls, f"{key} speaks at the model's own pace")
                self.assertGreater(ls, 1.2, f"{key} is too fast for narration")

    def test_multi_speaker_voice_declares_a_speaker(self):
        v = UrduVoice("en_free")
        self.assertIsNotNone(v.spec.get("speaker"))

    def test_unknown_voice_is_refused_early(self):
        from islamic.voice import VoiceError
        with self.assertRaises(VoiceError):
            UrduVoice("no-such-voice")


class TestFlowDecision(unittest.TestCase):
    """A chunk that ended a sentence gets more air than one that ended a clause."""

    def test_sentence_endings_are_recognised(self):
        for s in ("یہ ایک جملہ ہے۔", "کیا یہ سوال ہے؟", "Done.", "Really!"):
            self.assertTrue(_ends_sentence(s), s)

    def test_clause_endings_are_not(self):
        for s in ("یہ ایک جملہ ہے، اور", "کچھ نہیں;", "no trailing mark"):
            self.assertFalse(_ends_sentence(s), s)

    @staticmethod
    def _chunk(phonemes):
        class C:
            pass
        c = C()
        c.phonemes = list(phonemes)
        return c

    def test_a_sentence_chunk_ends_in_a_full_stop(self):
        """eSpeak keeps the punctuation in the phoneme string, which is how we
        know whether the engine made a sentence break or a clause break without
        re-parsing the text ourselves."""
        self.assertTrue(_chunk_ends_sentence(self._chunk("jeːh ˈeːk ɟˈʊmla hɛ.")))
        self.assertFalse(_chunk_ends_sentence(self._chunk("ɔr jeːh dˈuːsraː hɛ,")))

    def test_missing_phonemes_do_not_crash(self):
        self.assertFalse(_chunk_ends_sentence(self._chunk([])))


class TestTailSilence(unittest.TestCase):

    def test_measures_a_known_quiet_tail(self):
        sr = 22_050
        loud = (np.sin(np.arange(sr // 2) * 0.05) * 0.8).astype(np.float32)
        quiet = np.zeros(int(sr * 0.25), dtype=np.float32)
        got = _tail_silence(np.concatenate([loud, quiet]), sr)
        self.assertAlmostEqual(got, 0.25, delta=0.03)

    def test_a_chunk_with_no_tail_reports_nothing(self):
        sr = 22_050
        loud = (np.sin(np.arange(sr // 2) * 0.05) * 0.8).astype(np.float32)
        self.assertAlmostEqual(_tail_silence(loud, sr), 0.0, delta=0.03)

    def test_empty_chunk_is_safe(self):
        self.assertEqual(_tail_silence(np.zeros(0, dtype=np.float32), 22_050), 0.0)


class TestNarrateUsesFlow(unittest.TestCase):

    def test_flow_is_the_default(self):
        from islamic.narrate import narrate
        self.assertIs(inspect.signature(narrate).parameters["flow"].default, True)

    def test_narrate_can_still_be_asked_for_the_old_way(self):
        from islamic.narrate import narrate
        self.assertIn("flow", inspect.signature(narrate).parameters)

    def test_default_engine_is_the_piper_urdu_voice(self):
        from islamic.produce import DEFAULT_ENGINE
        self.assertEqual(VOICES[DEFAULT_ENGINE]["licence"], "MIT")

    def test_the_non_commercial_voice_is_not_the_default_anywhere(self):
        from islamic.produce import DEFAULT_ENGINE
        self.assertIn(DEFAULT_ENGINE, VOICES)
        self.assertNotIn("mm", DEFAULT_ENGINE)


class TestEnglishNormaliser(unittest.TestCase):

    def test_bracketed_footnote_is_removed(self):
        self.assertNotIn("2", english.normalize_for_speech_en("He said [2] that"))

    def test_parenthesised_note_number_is_removed(self):
        self.assertNotIn("(1)", english.normalize_for_speech_en("mercy (1) Indeed"))

    def test_digits_are_left_to_the_engine(self):
        """English reads 500 correctly on its own; expanding it by hand would
        only take away the engine's own judgement."""
        self.assertIn("500", english.normalize_for_speech_en("He gave 500 dinars"))

    def test_smart_punctuation_is_plain(self):
        out = english.normalize_for_speech_en("\u201cPeace\u201d \u2014 and mercy")
        self.assertNotIn("\u201c", out)
        self.assertNotIn("\u2014", out)

    def test_letters_are_preserved(self):
        """The opposite of the Urdu normaliser, which must strip Latin script."""
        out = english.normalize_for_speech_en("Say: He is Allah, the One.")
        self.assertEqual(out, "Say: He is Allah, the One.")


class TestTheNormalisersAreNotInterchangeable(unittest.TestCase):
    """Feeding an English script to the Urdu normaliser destroys it, and vice
    versa. `narrate` picks by voice language; this is why it must."""

    EN = "And of His signs is that He created for you mates."

    def test_urdu_normaliser_strips_latin(self):
        self.assertFalse(any(c.isascii() and c.isalpha()
                             for c in urdu.normalize_for_speech(self.EN)))

    def test_english_normaliser_keeps_it(self):
        self.assertIn("mates", english.normalize_for_speech_en(self.EN))

    def test_english_normaliser_keeps_urdu_too(self):
        """An English narration of a Qur'an translation can still quote Arabic."""
        self.assertIn("اللہ", english.normalize_for_speech_en("Say اللہ is One"))


class TestTheInstrumentItself(unittest.TestCase):
    """If the ruler is wrong, every measurement is wrong. These pin the ruler."""

    SR = 22_050

    def _write(self, path: Path, gaps: list[float]) -> None:
        # N gaps means N+1 tone blocks: the gaps sit *between* the blocks.
        block = int(self.SR * 1.0)
        tone = (np.sin(np.arange(block) * 0.05) * 0.8).astype(np.float32)
        parts = []
        for i in range(len(gaps) + 1):
            parts.append(tone)
            if i < len(gaps):
                parts.append(np.zeros(int(self.SR * gaps[i]), dtype=np.float32))
        x = np.concatenate(parts)
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(self.SR)
            f.writeframes((x * 32767).astype(np.int16).tobytes())

    def test_a_short_gap_is_not_a_pause(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            self._write(p, [0.10, 0.10])
            self.assertEqual(pauses(*self._load(p))["count"], 0)

    def test_a_long_gap_is_a_pause(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "b.wav"
            self._write(p, [0.30, 0.30])
            got = pauses(*self._load(p))
            self.assertEqual(got["count"], 2)
            self.assertAlmostEqual(got["mean_s"], 0.30, delta=0.04)

    def test_only_gaps_at_or_above_the_threshold_count(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "c.wav"
            self._write(p, [0.10, 0.30, 0.10])
            got = pauses(*self._load(p))
            self.assertEqual(got["count"], 1, "the 100 ms gaps must not count")
            self.assertAlmostEqual(got["longest_s"], 0.30, delta=0.04)

    def test_leading_and_trailing_silence_is_not_a_pause(self):
        """A file that starts with half a second of nothing has not paused."""
        with TemporaryDirectory() as d:
            p = Path(d) / "e.wav"
            self._write(p, [0.30])
            x, sr = self._load(p)
            padded = np.concatenate([np.zeros(sr // 2, np.float32), x,
                                     np.zeros(sr // 2, np.float32)])
            self.assertEqual(pauses(padded, sr)["count"], 1)

    def test_speech_plus_pauses_covers_the_file(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "f.wav"
            self._write(p, [0.30, 0.40])
            got = analyse(p)
            self.assertAlmostEqual(got["pauses"]["speech_s"] + got["pauses"]["total_s"],
                                   3.0 + 0.7, delta=0.12)

    def _load(self, p: Path):
        import soundfile as sf
        x, sr = sf.read(str(p), dtype="float32")
        return x, sr


if __name__ == "__main__":
    unittest.main(verbosity=2)
