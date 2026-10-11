"""
Authenticity gate: nothing reaches a video until its text and its grade check out.

Why this exists
---------------
`sources.py` guarantees that every word is *fetched*, never authored. That stops
fabrication, but it does not stop a **weak** narration: until 2026-10-11 a
hadith passed if its *collection* was on the trusted list. Sunan Ibn Majah is a
canonical collection - and it contains weak narrations. The clip we published
for `ibnmajah:224` ("seeking knowledge is a duty ... like a necklace ... around
the neck of swine") is graded **Very Da'if** by al-Albani, Muhammad Fu'ad Abd
al-Baqi and Shu'ayb al-Arna'ut, and Da'if by Zubair Ali Zai. The grades were
in the very payload we downloaded; nothing read them. This module reads them.

Two checks, both fail-closed
----------------------------
**Qur'an - two independent sources must agree on the Arabic.** The ayah comes
from api.alquran.cloud (Tanzil's Uthmani text). It is checked letter by letter
against api.quran.com (the Quran Foundation's own Uthmani text, a separate
pipeline). The two use slightly different Uthmani orthography (tatweel, where a
hamza sits, small high letters), so both are reduced to the consonantal
skeleton first - marks, tatweel and hamza carriers removed, alef forms unified -
and then the skeletons must be **identical**. One letter different and the
render stops.

**Hadith - the graders must agree it is acceptable.** The hadith-api payload
carries the gradings of named muhaddithin per narration. The rule:

* Sahih al-Bukhari and Sahih Muslim: accepted. Their authenticity is the
  consensus position of the scholars, and the dataset carries no per-hadith
  grade for them because none is needed.
* Every other collection: at least one grader must call it **sahih or hasan**,
  and **no** grader may call it da'if, munkar, shadh, mawdu' or batil. A
  disputed narration is refused, not averaged.
* A grade string this module does not recognise is a refusal, not a pass. A new
  wording in the dataset should stop the line until a person reads it.
* No grades at all, outside Bukhari/Muslim: refused.

Numbering is the second trap. Collections have several numbering schemes and
hadith-api uses its own for some (its `muslim:2699` is not the famous Muslim
2699). So a correct grade on the wrong hadith is possible, and the grade gate
alone cannot see it. That is what `check_relevance.py` is for: the topic's own
words must appear in the text that was fetched, so a hadith that is not about
the topic - including one fetched under the wrong number - cannot pass both.

What this does NOT replace
--------------------------
A scholar. The gate enforces the stated policy mechanically; it does not issue
rulings. The policy is deliberately conservative - it will refuse narrations a
scholar might accept - because a false refusal costs one video and a false
acceptance attributes a weak report to the Prophet (peace be upon him).

Usage:
    python3 -m islamic.verify quran:30:21 tirmidhi:2646
    python3 -m islamic.verify --library          # every clip in library.json
    python3 -m islamic.verify --catalogue        # every ref in topics.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .sources import CACHE, HADITH_CDN, ContentError, _get

ROOT = Path(__file__).resolve().parent.parent
QURAN_COM = "https://api.quran.com/api/v4/quran/verses/uthmani"
QURAN_CLOUD = "https://api.alquran.cloud/v1/ayah"

#: Collections whose authenticity is the consensus position. Nothing else is.
#: (This used to include the forty-hadith compilations. Those are anthologies,
#: not grading authorities, and the dataset carries no grades for them, so they
#: now go through the same rule as everything else - which means refused.)
CONSENSUS_SAHIH = {"bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim"}

# Order matters: "very daif" and "isnaad daif" must be seen as weak before
# anything looks for "sahih" inside them, and "hasan" in "hasan lighairihi"
# is still hasan.
_WEAK = re.compile(r"da'?e?e?if|daeef|dhaif|munkar|shadh|shaadh|mawdu|maudu|"
                   r"mawdoo|fabricat|batil|baatil|matruk|matrook|weak|"
                   r"no basis|la asla|munqati|mursal", re.I)
_STRONG = re.compile(r"sahih|saheeh|sahi\b|hasan|qawi|jayyid|thabit", re.I)


@dataclass
class Verdict:
    ref: str
    ok: bool
    grade_line: str = ""             # what the card prints, Latin only
    reasons: list[str] = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def line(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        why = "; ".join(self.reasons)
        return f"{mark}  {self.ref:18s} {self.grade_line or '-'}" + (f"   ({why})" if why else "")


# ---------------------------------------------------------------------------
# Qur'an
# ---------------------------------------------------------------------------

_ALEF = str.maketrans({"ٱ": "ا", "أ": "ا", "إ": "ا", "آ": "ا", "ٰ": "",
                       "ى": "ي", "ی": "ي", "ک": "ك", "ۀ": "ه", "ة": "ه",
                       "ؤ": "و", "ئ": "ي", "ء": "", "ـ": ""})


def skeleton(text: str) -> str:
    """The consonantal skeleton of Uthmani text.

    Drops every combining mark (harakat, small high letters, Qur'anic annotation
    signs - all category Mn/Me, or Cf for the few formatting ones), the tatweel,
    the standalone hamza, and unifies alef and hamza-carrier forms. What is left
    is the letters, which is exactly what two honest Uthmani editions must agree
    on even when their orthographic conventions differ.
    """
    out = []
    for ch in unicodedata.normalize("NFC", text):
        cat = unicodedata.category(ch)
        if cat in ("Mn", "Me", "Cf"):
            continue
        if "\u06d6" <= ch <= "\u06ed":          # Qur'anic annotation block
            continue
        out.append(ch)
    s = "".join(out).translate(_ALEF)
    # Two spellings of one word are a convention, not a variant reading, and
    # both editions are the same Hafs text: يـٰ / يا, the elided alef of ٱلرَّحْمَٰن.
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ", "")


def _ayahs(ref: str) -> list[str]:
    """'30:21' -> ['30:21']; '83:1-3' -> ['83:1', '83:2', '83:3']."""
    s, _, a = ref.partition(":")
    if "-" in a:
        lo, hi = (int(x) for x in a.split("-"))
        return [f"{s}:{n}" for n in range(lo, hi + 1)]
    return [f"{s}:{a}"]


def verify_quran(locator: str) -> Verdict:
    ref = f"quran:{locator}"
    v = Verdict(ref, True, "Qur'an - text agreed by 2 independent sources")
    for key in _ayahs(locator):
        try:
            a = _get(f"{QURAN_CLOUD}/{key}/quran-uthmani", f"vq_cloud_{key}")
            b = _get(f"{QURAN_COM}?verse_key={key}", f"vq_com_{key}")
        except ContentError as e:
            return Verdict(ref, False, "", [f"{key}: a source is unreachable ({e})"])
        ta = (a.get("data") or {}).get("text", "")
        verses = b.get("verses") or []
        tb = verses[0].get("text_uthmani", "") if verses else ""
        if not ta or not tb:
            return Verdict(ref, False, "", [f"{key}: one source returned no text"])
        # Tanzil prefixes the first ayah of each surah with the basmala; the
        # Quran Foundation does not. It is not part of the ayah's own text.
        sa, sb = skeleton(ta), skeleton(tb)
        bism = skeleton("بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ")
        if key.endswith(":1") and not key.startswith(("1:", "9:")) and sa.startswith(bism):
            sa = sa[len(bism):]
        if sa != sb:
            i = next((n for n, (x, y) in enumerate(zip(sa, sb)) if x != y),
                     min(len(sa), len(sb)))
            v.ok = False
            v.reasons.append(f"{key}: sources disagree at letter {i}: "
                             f"{sa[max(0, i - 6):i + 6]!r} vs {sb[max(0, i - 6):i + 6]!r}")
        v.detail[key] = {"letters": len(sa)}
    if not v.ok:
        v.grade_line = ""
    return v


# ---------------------------------------------------------------------------
# Hadith
# ---------------------------------------------------------------------------

def classify(grade: str) -> str:
    """'weak' | 'strong' | 'unknown' for one grader's verdict."""
    g = grade.strip()
    if _WEAK.search(g):
        return "weak"
    if _STRONG.search(g):
        return "strong"
    return "unknown"


def judge(collection: str, grades: list[dict]) -> tuple[bool, str, list[str]]:
    """Apply the policy to one narration's gradings.

    Separated from the network so the policy is unit-testable on exactly the
    gradings that taught it - including ibnmajah:224.
    """
    if collection in CONSENSUS_SAHIH:
        return True, f"Sahih - {CONSENSUS_SAHIH[collection]}", []
    if not grades:
        return False, "", ["no grading in the source; outside Bukhari/Muslim "
                           "that is a refusal"]
    weak = [g for g in grades if classify(g.get("grade", "")) == "weak"]
    strong = [g for g in grades if classify(g.get("grade", "")) == "strong"]
    unknown = [g for g in grades if classify(g.get("grade", "")) == "unknown"]

    def who(gs):
        return ", ".join(f"{g.get('name', '?')}: {g.get('grade', '?')}" for g in gs)

    reasons = []
    if weak:
        reasons.append(f"graded weak by {who(weak)}")
    if unknown:
        reasons.append(f"unrecognised grade wording, needs a person: {who(unknown)}")
    if not strong:
        reasons.append("no grader calls it sahih or hasan")
    if reasons:
        return False, "", reasons

    # The card line: the strongest single word, and who said it. Latin only -
    # the footer is drawn in DejaVu, which has no Arabic.
    words = " ".join(g["grade"] for g in strong).lower()
    head = "Sahih" if "sahih" in words else "Hasan"
    names = []
    for g in strong:
        n = _short_name(g.get("name", ""))
        if n and n not in names:
            names.append(n)
    return True, f"{head} - graded by {', '.join(names[:3])}", []


def _short_name(name: str) -> str:
    """'Al-Albani' stays; 'Ahmad Muhammad Shakir' -> 'Ahmad Shakir'."""
    parts = name.replace("  ", " ").split()
    if len(parts) <= 2:
        return name
    return f"{parts[0]} {parts[-1]}"


def verify_hadith(collection: str, number: str) -> Verdict:
    ref = f"{collection}:{number}"
    try:
        d = _get(f"{HADITH_CDN}/eng-{collection}/{number}.json",
                 f"h_{collection}_eng_{number}")
    except ContentError as e:
        return Verdict(ref, False, "", [f"unreachable ({e})"])
    hs = d.get("hadiths") or []
    if not hs:
        return Verdict(ref, False, "", ["not found in the source"])
    h = hs[0]
    if not (h.get("text") or "").strip():
        return Verdict(ref, False, "", ["the source has no text for this number"])
    ok, line, reasons = judge(collection, h.get("grades") or [])
    return Verdict(ref, ok, line, reasons, {"grades": h.get("grades") or []})


# ---------------------------------------------------------------------------

def verify(ref: str) -> Verdict:
    src, _, loc = ref.partition(":")
    if src == "quran":
        return verify_quran(loc)
    return verify_hadith(src, loc)


def require(ref: str) -> Verdict:
    """Verify, or raise. For callers that must not proceed on a failure."""
    v = verify(ref)
    if not v.ok:
        raise ContentError(f"{ref} refused by the authenticity gate: "
                           + "; ".join(v.reasons))
    return v


def _library_refs() -> list[str]:
    d = json.loads((ROOT / "library.json").read_text(encoding="utf-8"))
    return [c["ref"] for c in d["clips"]]


def _catalogue_refs() -> list[str]:
    from . import topics
    seen, out = set(), []
    for t in topics.list_topics():
        for r in topics.refs_for(t):
            if r not in seen:
                seen.add(r)
                out.append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Authenticity gate")
    ap.add_argument("refs", nargs="*")
    ap.add_argument("--library", action="store_true", help="every clip in library.json")
    ap.add_argument("--catalogue", action="store_true", help="every ref in topics.py")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    refs = list(a.refs)
    if a.library:
        refs += _library_refs()
    if a.catalogue:
        refs += _catalogue_refs()
    if not refs:
        ap.error("give refs, --library or --catalogue")
    results = [verify(r) for r in refs]
    if a.json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(r.line())
        bad = sum(not r.ok for r in results)
        print(f"\n{len(results) - bad}/{len(results)} pass the authenticity gate")
    return 1 if any(not r.ok for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
