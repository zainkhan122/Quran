"""
Verbatim Islamic content sources.

DESIGN RULE, NON-NEGOTIABLE
---------------------------
This module never contains, generates or paraphrases a single word of Quranic
or hadith text. Every character of sacred text comes from a citable dataset,
fetched at build time, and is stored with its reference.

Why it is built this way: a language model that "remembers" a hadith number or
wording invents them with total confidence. Fabricated hadith (hadith mawdu')
is a grave matter in Islamic tradition, and a pipeline that can hallucinate a
narration is worse than no pipeline. Fetching removes the failure mode instead
of asking a reviewer to catch it.

Sources (both free, no API key, no attribution fee):
  Quran  : api.alquran.cloud   - Uthmani Arabic + Jalandhry Urdu + Sahih English
  Hadith : fawazahmed0/hadith-api via jsDelivr - Bukhari, Muslim, Abu Dawud,
           Tirmidhi, Ibn Majah, Nasai, Malik, Nawawi 40, Qudsi 40, Dehlawi 40
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

QURAN_API = "https://api.alquran.cloud/v1"
HADITH_CDN = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions"

#: Network cache. It is deliberately OUTSIDE the repo.
#:
#: It used to be `.content-cache/` in the project root, and it grew to 32 MB of
#: fetched hadith editions and verse payloads. The workspace snapshot excludes
#: `.cache/` but not `.content-cache/`, so that 32 MB was charged against the
#: project's 128 MB budget on every single session - and it is the reason a
#: snapshot once came up over budget and dropped 22 files, including the git
#: objects for a finished commit. A cache belongs in a cache directory.
CACHE = Path.home() / ".cache" / "islamic-studio"

# Hadith collections this pipeline trusts enough to put on a video, with the
# grade the collection itself carries. Anything absent from this map is refused.
TRUSTED_COLLECTIONS: dict[str, str] = {
    "bukhari":  "Sahih al-Bukhari",
    "muslim":   "Sahih Muslim",
    "nawawi":   "Forty Hadith of an-Nawawi",
    "qudsi":    "Forty Hadith Qudsi",
    "dehlawi":  "Forty Hadith of Shah Waliullah Dehlawi",
    "abudawud": "Sunan Abu Dawud",
    "tirmidhi": "Jami at-Tirmidhi",
    "ibnmajah": "Sunan Ibn Majah",
    "nasai":    "Sunan an-Nasai",
    "malik":    "Muwatta Malik",
}
# Collections whose contents are sahih by the compiler's own criterion.
INTRINSICALLY_SAHIH = {"bukhari", "muslim", "nawawi", "qudsi", "dehlawi"}

# Collections that carry an Urdu edition in the source API. Others are
# Arabic + English only, which is fine for cards but means no Urdu narration.
HAS_URDU = {"bukhari", "muslim", "abudawud", "tirmidhi", "ibnmajah", "nasai"}


class ContentError(RuntimeError):
    pass


def _get(url: str, cache_key: str, ttl_days: int = 30) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (re.sub(r"[^A-Za-z0-9_.-]", "_", cache_key)[:120] + ".json")
    if f.exists() and (time.time() - f.stat().st_mtime) / 86400 < ttl_days:
        return json.loads(f.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "islamic-video-studio/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ContentError(f"fetch failed for {url}: {e}") from e
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


@dataclass
class VerbatimItem:
    """One on-screen quote. Every field is fetched, never authored."""
    kind: str                  # "quran" | "hadith"
    arabic: str
    urdu: str
    english: str
    source: str                # Latin-only citation, safe in a Latin font
    reference: str             # machine key, e.g. "quran:65:2" / "bukhari:1"
    source_ar: str = ""        # same citation in Arabic script, when available
    grade: str = ""
    topic: str = ""
    surah_name: str = ""
    collected_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))

    def validate(self) -> None:
        """Hard gate before anything reaches a video.

        Not every collection has an Urdu edition in the source API (Nawawi 40,
        Qudsi 40 and Dehlawi 40 ship Arabic + English only), so we require at
        least one usable language rather than all three — but we always require
        a citation, and we always require that an `arabic` field really is
        Arabic script. A card with invented or garbled Arabic is the one
        failure this whole module exists to prevent.
        """
        missing = [k for k in ("source", "reference") if not getattr(self, k)]
        if missing:
            raise ContentError(f"refusing to render {self.reference!r}: missing {missing}")
        if not (self.arabic or self.urdu or self.english):
            raise ContentError(f"{self.reference}: no text in any language")
        if self.arabic and not re.search(r"[\u0600-\u06FF]", self.arabic):
            raise ContentError(f"{self.reference}: arabic field has no Arabic script")
        if self.urdu and not re.search(r"[\u0600-\u06FF]", self.urdu):
            raise ContentError(f"{self.reference}: urdu field has no Arabic script")
        if self.kind == "hadith":
            coll = self.reference.split(":")[0]
            if coll not in TRUSTED_COLLECTIONS:
                raise ContentError(f"collection {coll!r} is not on the trusted list")


# ---------------------------------------------------------------------------
# Quran
# ---------------------------------------------------------------------------

def quran(ref: str, topic: str = "") -> list[VerbatimItem]:
    """ref: '65:2' or '65:2-4' or '2:255'"""
    parts = ref.split("-")
    start = parts[0]
    ayahs = [start] if len(parts) == 1 else [
        f"{start.split(':')[0]}:{n}"
        for n in range(int(start.split(":")[1]), int(parts[1].split(":")[-1]) + 1)
    ]
    items: list[VerbatimItem] = []
    for a in ayahs:
        d = _get(f"{QURAN_API}/ayah/{a}/editions/quran-uthmani,ur.jalandhry,en.sahih",
                 f"quran_{a}")
        if d.get("code") != 200:
            raise ContentError(f"Quran {a}: {d.get('status')}")
        by = {e["edition"]["identifier"]: e for e in d["data"]}
        ar = by.get("quran-uthmani", {}).get("text", "").strip()
        ur = by.get("ur.jalandhry", {}).get("text", "").strip()
        en = by.get("en.sahih", {}).get("text", "").strip()
        meta = next(iter(by.values()))
        items.append(VerbatimItem(
            kind="quran", arabic=ar, urdu=ur, english=en,
            # Latin only: PIL does no font fallback, so a mixed-script footer
            # renders the Latin half as tofu boxes.
            source=f"Qur'an {meta['surah']['number']}:{meta['numberInSurah']} · "
                   f"{meta['surah']['englishName']}",
            # the API's name field already begins with "سُورَةُ"; prefixing it
            # again produced "سورۃ سورة الروم"
            source_ar=f"{meta['surah']['name']} · آیت {meta['numberInSurah']}",
            reference=f"quran:{a}", grade="Quran", topic=topic,
            surah_name=meta["surah"]["name"],
        ))
    for i in items:
        i.validate()
    return items


# ---------------------------------------------------------------------------
# Hadith
# ---------------------------------------------------------------------------

def hadith(collection: str, number: int, topic: str = "") -> VerbatimItem:
    if collection not in TRUSTED_COLLECTIONS:
        raise ContentError(
            f"collection {collection!r} not trusted. Choose from: "
            f"{', '.join(sorted(TRUSTED_COLLECTIONS))}")

    def fetch(lang: str) -> dict | None:
        try:
            d = _get(f"{HADITH_CDN}/{lang}-{collection}/{number}.json",
                     f"h_{collection}_{lang}_{number}")
            return (d.get("hadiths") or [None])[0]
        except ContentError:
            return None

    ara, urd, eng = fetch("ara"), fetch("urd"), fetch("eng")
    if ara is None and eng is None:
        raise ContentError(f"{collection}:{number} not found")

    name = TRUSTED_COLLECTIONS[collection]
    grade = ("Sahih (by the compiler's criterion)" if collection in INTRINSICALLY_SAHIH
             else "See a scholar — this collection contains a range of grades")

    item = VerbatimItem(
        kind="hadith",
        arabic=(ara or {}).get("text", "").strip(),
        urdu=(urd or {}).get("text", "").strip(),
        english=(eng or {}).get("text", "").strip(),
        source=f"{name}, Hadith {number}",
        reference=f"{collection}:{number}",
        grade=grade,
        topic=topic,
    )
    # For collections where the Arabic edition is unavailable, fall back to the
    # English body for the card rather than inventing Arabic.
    if not item.arabic and item.english:
        item.arabic = ""
    item.validate()
    return item


def clean_isnad(text: str, max_lead: int = 220) -> str:
    """Trim a narrator chain for readability WITHOUT touching the matn.

    Only cuts a leading 'Narrated X:' style prefix or a long isnad before the
    actual saying. The remaining text is always a verbatim substring — this
    never rewrites, joins or paraphrases anything.
    """
    if not text:
        return text
    t = re.sub(r"^\s*Narrated\s+[^:]{1,80}:\s*", "", text).strip()
    # Urdu editions often open with a long chain ending in a colon
    if len(t) > max_lead:
        m = re.search(r"[:：]", t[:max_lead + 120])
        if m and m.start() > 60:
            t = t[m.start() + 1:].strip()
    return t


# Phrases that only appear inside a chain of narrators (isnad) in the Urdu
# editions of the large collections.
_ISNAD_MARKERS = [
    "بیان کی", "بیان کیا", "روایت کی", "روایت ہے", "سے روایت",
    "ہم کو", "ہمیں", "حدثنا", "أخبرنا", "انہوں نے کہا کہ",
    "بن سعید", "بن ابراہیم", "بن عبد", "رضی اللہ عنہ سے",
]


def has_isnad(text: str) -> bool:
    """True if this text opens with a chain of narrators.

    We DETECT rather than trim, and that decision is deliberate. An earlier
    attempt trimmed at the first "نے کہا" — which in Urdu isnad chains means
    "he said that [the next narrator]...", so it cut in the middle of the
    chain and left the rest of the narrator list presented as if it were the
    hadith. Silently mis-cutting sacred text is a worse failure than not
    narrating it, so this function never modifies anything.
    """
    if not text:
        return False
    head = text[:400]
    hits = sum(1 for m in _ISNAD_MARKERS if m in head)
    return hits >= 2


def load_items(refs: list[str], topic: str = "") -> list[VerbatimItem]:
    """refs like ['quran:65:2', 'bukhari:1', 'muslim:2699']"""
    out: list[VerbatimItem] = []
    for r in refs:
        kind, _, rest = r.partition(":")
        if kind == "quran":
            out.extend(quran(rest, topic))
        elif kind in TRUSTED_COLLECTIONS:
            out.append(hadith(kind, int(rest), topic))
        else:
            raise ContentError(f"unknown reference {r!r}")
    return out


def save(items: list[VerbatimItem], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2),
                 encoding="utf-8")
