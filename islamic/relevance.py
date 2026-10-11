"""
Does the topic we put on screen actually appear in the verse we are showing?

The rule the reviewer gave us
-----------------------------
One clip paired the topic *"Daughters — a blessing to be cherished"* with
Qur'an 81:8, "and when the girl who was buried alive is asked". The verdict was
one line: *"its topic and actual ayah has NO relation. Such topic/ayah to be
avoided."*

That verdict is correct, and it is worth being precise about why, because the
naive objection ("81:8 is about girls, the topic is about girls") is exactly
the reasoning that produced the bad clip. 81:8 is about a **crime** — the
pre-Islamic practice of burying infant daughters. The headline asserted a
**blessing**. The subject matched; the claim did not. A single shared noun is
not a relation.

So the check here is not "do the topic and the ayah share a keyword". It is:

    every claim the headline makes must be traceable to words the verse uses.

Concretely, each topic declares

    claims    a claim-key -> the Urdu surface forms that substantiate it
    requires  the claim-keys the on-screen headline actually asserts

and a pairing passes only if **every** required claim is matched inside the
verse's own Urdu translation. `daughters` requires `daughters` **and**
`blessing`; 81:8 supplies the first and never the second, so it fails, and it
keeps failing no matter how the headline is reworded — which is the point.

Two consequences worth stating plainly:

* this is a *lexical* check on a *translation*. It cannot certify that a
  translation is theologically right, and it cannot read context. It is a
  tripwire for the specific failure mode above, not a substitute for review;
* because it reads the Urdu translation fetched from the publisher, it runs
  against the same text the clip will display. There is no second copy of the
  verse to drift out of step.

Usage (see tools/check_relevance.py for the CLI):
    from islamic.relevance import check
    check("daughters", "اور جب لڑکی سے جو زندہ دفنا دی گئی ہو پوچھا جائے گا").ok  # False
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Urdu function words and particles. Capitalisation gives no hint in an
# abjad-derived script, so we carry an explicit list.
STOPWORDS = {
    "اور", "کہ", "سے", "کا", "کی", "کے", "کو", "میں", "پر", "ہے", "ہیں",
    "نے", "تو", "بھی", "جو", "یہ", "وہ", "اس", "ان", "ایک", "نہ", "ہو",
    "ہوکر", "کر", "کرنا", "کرتے", "کہتے", "ہوا", "ہوئے", "لیے", "ہی",
    "اللہ", "رسول", "صلی", "علیہ", "وسلم", "رضی", "عنہ", "کہ",
}

_SUFFIXES = ("وں", "ائیں", "ایں", "ات", "یں", "ے", "ی", "ہ", "ا")
_MIN_STEM = 3


#: Letters that publishers spell inconsistently. Urdu mixes the Arabic and the
#: Urdu codepoints freely: the same word comes back as عائشہ with U+06C1 or with
#: U+0629, and "آڑ" arrives either precomposed (U+0622) or as ا + U+0653 maddah.
#: Matching on the raw bytes silently fails on exactly the words we care about,
#: so everything is folded to the Urdu block before comparison.
LETTER_FOLD = str.maketrans({
    "\u064a": "\u06cc",   # ي  -> ی
    "\u0649": "\u06cc",   # ى  -> ی
    "\u0643": "\u06a9",   # ك  -> ک
    "\u0622": "\u0627",   # آ  -> ا
    "\u0623": "\u0627",   # أ  -> ا
    "\u0625": "\u0627",   # إ  -> ا
    "\u0671": "\u0627",   # ٱ  -> ا
    "\u0629": "\u06c1",   # ة  -> ہ
    "\u06c3": "\u06c1",   # ۃ  -> ہ
    "\u0640": "",         # ـ  tatweel
})


def strip_marks(text: str) -> str:
    """Fold to one spelling per letter, then drop harakat and waqf marks.

    Composed first (NFC) so ا + U+0653 becomes the single codepoint آ before the
    combining mark is removed - otherwise the maddah is dropped and "آڑ" (a
    shield) silently becomes "اڑ" (to rise), which is a different word.
    """
    text = unicodedata.normalize("NFC", text)
    return "".join(c for c in text
                   if not unicodedata.category(c).startswith("M")
                   and c not in "\u06d6\u06d7\u06d8\u06d9\u06da\u06db\u06dc\u06dd\u06de\u06df\u06e0\u06e1\u06e2\u06e3\u06e4\u06e5\u06e6\u06e7\u06e8\u06e9\u06ea").translate(LETTER_FOLD)


def stem(token: str) -> str:
    """Crude but deterministic Urdu stemmer: peel one inflectional suffix.

    Urdu is heavily inflected (بیٹی / بیٹیاں / بیٹیوں). A full morphological
    analyser is out of scope; peeling one suffix and comparing stems fixes the
    cases that actually occur in this copy without inventing matches.
    """
    t = strip_marks(token).strip("،۔؟!:؛-")
    for suf in _SUFFIXES:
        if len(t) - len(suf) >= _MIN_STEM and t.endswith(suf):
            return t[: -len(suf)]
    return t


def tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[^\w\u0600-\u06ff\u0750-\u077f]+", strip_marks(text)) if w]


def content_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if stem(t) not in STOPWORDS and len(t) > 1]


@dataclass
class RelevanceReport:
    topic: str
    ok: bool
    matched: dict[str, list[str]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    shares: dict[str, float] = field(default_factory=dict)
    words: int = 0

    @property
    def reason(self) -> str:
        if self.ok:
            hit = "; ".join(f"{k}<-{','.join(v[:2])}" for k, v in self.matched.items())
            return f"topic '{self.topic}' is carried by the text: {hit}"
        detail = "; ".join(
            f"headline asserts '{k}' but the text never says it "
            f"(looked for: {', '.join(self._forms(k))})" for k in self.missing)
        return f"topic '{self.topic}' does not survive the text: {detail}"

    _forms_lookup: dict = field(default_factory=dict, repr=False)

    def _forms(self, key: str) -> list[str]:
        return self._forms_lookup.get(key, [])


def _matches(forms: list[str], present: set[str], raw_tokens: set[str]) -> list[str]:
    """Which declared surface forms occur in the text, stem-wise."""
    out = []
    for form in forms:
        s = stem(form)
        if not s:
            continue
        if s in present or any(t.startswith(s) and len(t) - len(s) <= 3 for t in raw_tokens):
            out.append(form)
    return out


def check(topic_key: str, text: str, topics: dict | None = None) -> RelevanceReport:
    """Score `text` (the Urdu translation / hadith body) against a topic."""
    if topics is None:
        from .topics import TOPICS
        topics = TOPICS

    spec = topics.get(topic_key)
    if spec is None:
        return RelevanceReport(topic_key, False, missing=[f"unknown topic '{topic_key}'"])

    claims: dict[str, list[str]] = spec.get("claims", {})
    requires: list[str] = spec.get("requires", list(claims))

    present = {stem(t) for t in tokens(text)}
    raw_tokens = set(tokens(text))

    matched: dict[str, list[str]] = {}
    missing: list[str] = []
    shares: dict[str, float] = {}

    n_content = max(len(content_tokens(text)), 1)
    for key in requires:
        forms = claims.get(key, [])
        hit = _matches(forms, present, raw_tokens)
        if hit:
            matched[key] = hit
            # how much of the text this claim accounts for
            shares[key] = round(
                sum(1 for t in content_tokens(text)
                    if any(stem(t).startswith(stem(h)) for h in hit)) / n_content, 3)
        else:
            missing.append(key)

    rep = RelevanceReport(topic=topic_key, ok=not missing, matched=matched,
                          missing=missing, shares=shares,
                          words=len(content_tokens(text)))
    rep._forms_lookup = {k: claims.get(k, []) for k in missing}
    return rep


# ---------------------------------------------------------------------------
# Where the text comes from
# ---------------------------------------------------------------------------

WEB = ROOT / "web" / "video"
OUTPUT = ROOT / "output" / "video"


def text_from_record(slug: str) -> str | None:
    """The Urdu body that was actually rendered, from the published record."""
    # output/ first: inside a render job that is the clip we just built, and it
    # is the one being gated. On a bare checkout only web/ exists, so a
    # published clip is still auditable offline.
    for d in (OUTPUT, WEB):
        p = d / f"{slug}.build.json"
        if p.exists():
            rec = json.loads(p.read_text(encoding="utf-8"))
            body = rec.get("urdu") or ""
            if body:
                return body
    return None


def text_from_publisher(ref: str, topic: str = "") -> str:
    """Fetch the Urdu translation/body the renderer itself will use."""
    from .sources import load_items
    items = load_items([ref], topic)
    if not items:
        raise RuntimeError(f"no text returned for {ref}")
    body = "\n".join((getattr(i, "urdu", "") or "") for i in items).strip()
    if not body:
        raise RuntimeError(f"{ref} came back with no Urdu text")
    return body


def text_for(ref: str, slug: str, *, offline: bool = False,
             topic: str = "") -> tuple[str, str]:
    """Return (text, provenance). Offline prefers the rendered artefact.

    Offline mode exists so the test suite can audit the clip that was built
    rather than a fresh download that may have changed under us; online mode is
    what the plan job uses, because at plan time there is no artefact yet.
    """
    if offline:
        t = text_from_record(slug)
        if t:
            return t, "build record"
        raise RuntimeError(f"offline and no build record for {slug}")
    return text_from_publisher(ref, topic), "publisher"
