"""
Topic collections.

`label`    is the short name used in file names and metadata.
`headline` is the on-screen topic: explanatory, not a single word, and short
           enough to set in ONE line per language. Written by us, never
           attributed to scripture.

This file contains REFERENCES ONLY — surah:ayah coordinates and hadith numbers.
It never contains sacred text. Text is always fetched verbatim at build time
(see sources.py), so a mistake here can mislabel which video a verse lands in,
but it can never corrupt the verse itself.

Every topic below is a list of references a human should verify before
publishing. `search` helps find additional hadith numbers by keyword.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .sources import HADITH_CDN, TRUSTED_COLLECTIONS, _get

# ---------------------------------------------------------------------------
TOPICS: dict[str, dict] = {
    "marriage": {
        "label": {"en": "Marriage", "ur": "نکاح"},
        "headline": {"en": "Marriage — love and mercy between spouses", "ur": "نکاح — میاں بیوی کے درمیان محبت اور رحمت"},
        "quran": ["30:21", "4:1", "65:2-3", "2:187", "24:32"],
        "hadith": [],
        "note": "Pairs well with the famous 'mawadda wa rahma' ayah (30:21).",
    },
    "children": {
        "label": {"en": "Children", "ur": "اولاد"},
        "headline": {"en": "Children — raise them with love and du'a", "ur": "اولاد — محبت اور دعا کے ساتھ پرورش"},
        "quran": ["25:74", "66:6", "17:24", "31:13-14"],
        "hadith": [],
        "note": "17:24 is about kindness to parents; 25:74 is the du'a for family.",
    },
    "daughters": {
        "label": {"en": "Daughters", "ur": "بیٹیاں"},
        "headline": {"en": "Daughters — a blessing to be cherished", "ur": "بیٹیاں — ایک عظیم نعمت"},
        "quran": ["81:8-9", "16:97", "17:31", "42:49-50"],
        "hadith": [],
        "note": "81:8-9 condemns the pre-Islamic practice of burying daughters; "
                "search the collections for the hadith on raising daughters well.",
    },
    "business": {
        "label": {"en": "Business & trade", "ur": "کاروبار"},
        "headline": {"en": "Trade — honesty in every deal", "ur": "کاروبار — ہر معاملے میں دیانت"},
        "quran": ["2:275", "2:282", "62:10", "4:29", "83:1-3"],
        "hadith": [],
        "note": "2:282 is the longest ayah in the Quran — the contract-writing verse.",
    },
    "women": {
        "label": {"en": "Women", "ur": "عورتوں کے حقوق"},
        "headline": {"en": "Women — equal reward, equal dignity", "ur": "عورتیں — برابر اجر، برابر عزت"},
        "quran": ["33:35", "4:1", "16:97", "4:19", "9:71"],
        "hadith": [],
        "note": "33:35 names men and women in parallel for every spiritual rank.",
    },
    "parents": {
        "label": {"en": "Parents", "ur": "والدین"},
        "headline": {"en": "Parents — kindness in their old age", "ur": "والدین — بڑھاپے میں حسنِ سلوک"},
        "quran": ["17:23-24", "31:14-15", "46:15"],
        "hadith": [],
    },
    "knowledge": {
        "label": {"en": "Knowledge", "ur": "علم"},
        "headline": {"en": "Knowledge — a path that never ends", "ur": "علم — ایسا راستہ جو کبھی ختم نہ ہو"},
        "quran": ["96:1-5", "20:114", "39:9", "58:11"],
        "hadith": [],
    },
    "prayer": {
        "label": {"en": "Prayer & du'a", "ur": "دعا"},
        "headline": {"en": "Du'a — turning to Him at every moment", "ur": "دعا — ہر لمحے اُسی کی طرف رجوع"},
        "quran": ["2:186", "40:60", "7:55-56", "2:201"],
        "hadith": [],
    },
}


def list_topics() -> list[str]:
    return sorted(TOPICS)


def get(topic: str) -> dict:
    if topic not in TOPICS:
        raise KeyError(f"unknown topic {topic!r}; try: {', '.join(list_topics())}")
    return TOPICS[topic]


def refs_for(topic: str) -> list[str]:
    t = get(topic)
    return [f"quran:{r}" for r in t.get("quran", [])] + \
           [f"{h}" for h in t.get("hadith", [])]


def search(collection: str, keyword: str, language: str = "eng",
           limit: int = 10) -> list[tuple[int, str]]:
    """Keyword search inside a hadith edition. Returns [(number, snippet)].

    Search is a discovery aid only — it tells you WHERE to look. Always open the
    returned reference and read the full text before putting it on a video.
    """
    if collection not in TRUSTED_COLLECTIONS:
        raise KeyError(f"unknown collection {collection!r}")
    data = _get(f"{HADITH_CDN}/{language}-{collection}.json",
                f"full_{collection}_{language}", ttl_days=90)
    hits: list[tuple[int, str]] = []
    for h in data.get("hadiths", []):
        body = h.get("text", "")
        if re.search(re.escape(keyword), body, re.IGNORECASE):
            hits.append((int(h.get("hadithnumber", 0)), body))
            if len(hits) >= limit:
                break
    return hits


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        for n, txt in search(sys.argv[2], sys.argv[3]):
            print(f"{n}: {txt[:180]}")
    else:
        print(json.dumps({k: v.get("quran") for k, v in TOPICS.items()},
                         ensure_ascii=False, indent=2))
