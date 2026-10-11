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
        "claims": {
            "spouses": ["میاں", "بیوی", "بیویوں", "عورت", "عورتیں", "عورتوں", "نکاح", "شادی", "جوڑا", "زوجیت", "ازواج", "مرد"],
            "love": ["محبت", "مودت", "مہربانی", "مہربان", "رحمت", "پیار", "الفت", "فضل"],
        },
        "requires": ["spouses"],
        "quran": ["30:21", "4:1", "2:187", "24:32"],
        "hadith": [],
        "note": "30:21 is the 'mawadda wa rahma' ayah. 65:2-3 was here and did not "
                "survive the relevance check (it is about 'iddah and taqwa, not about "
                "the spouses' bond) - pruned rather than reworded.",
    },
    "children": {
        "label": {"en": "Children", "ur": "اولاد"},
        "headline": {"en": "Children — raise them with care and du'a", "ur": "اولاد — پرورش اور دعا کے ساتھ"},
        "claims": {
            "children": ["اولاد", "بچے", "بچوں", "بیٹا", "بیٹے", "بیٹی", "بیٹیاں", "لڑکا", "لڑکی", "فرزند", "عیال"],
            "care": ["پرورش", "پالنا", "پالتی", "تربیت", "دعا", "شفقت", "محبت", "رزق", "بچاؤ", "نصیحت", "سلوک", "بچپن"],
        },
        "requires": ["children", "care"],
        "quran": ["25:74", "66:6", "31:13-14"],
        "hadith": [],
        "note": "17:24 was listed here but its words are about kindness TO parents, not "
                "about raising children - it stays in the 'parents' topic only.",
    },
    "daughters": {
        "label": {"en": "Daughters", "ur": "بیٹیاں"},
        "headline": {"en": "Daughters — a gift, and a shield from the Fire",
                     "ur": "بیٹیاں — اللہ کی عطا، اور جہنم سے آڑ"},
        "claims": {
            "daughters": ["بیٹی", "بیٹیاں", "بیٹیوں", "لڑکی", "لڑکیاں", "لڑکیوں", "دختر"],
            # the positive worth of daughters: given as a gift, or named as a
            # protection/reward. Deliberately does NOT include bare nouns.
            "worth": ["عطا", "عنایت", "بخش", "نعمت", "آڑ", "جنت", "نجات", "اجر", "ثواب", "صلہ", "بھلائی"],
        },
        "requires": ["daughters", "worth"],
        "quran": ["42:49-50"],
        "hadith": ["tirmidhi:1913"],
        # tirmidhi:1912 (Da'if by Shakir, al-Albani, Zai) and tirmidhi:1916
        # (disputed: Da'if by Shakir and al-Albani, Hasan by two others) were
        # removed 2026-10-11 by the authenticity gate. Disputed means refused.,
        "note": "81:8 previously sat here under the headline 'a blessing to be "
                "cherished'. It is about the CRIME of burying infant daughters - the "
                "subject matched, the claim did not. It now belongs to 'justice', and "
                "this topic is carried by verses and hadith that actually say daughters "
                "are a gift and a protection (Tirmidhi 1913: 'they will be a barrier "
                "from the Fire'; 42:49-50: 'He grants daughters to whom He wills').",
    },
    "business": {
        "label": {"en": "Business & trade", "ur": "کاروبار"},
        "headline": {"en": "Trade — honesty in every deal", "ur": "کاروبار — ہر معاملے میں دیانت"},
        "claims": {
            "trade": ["کاروبار", "تجارت", "سودا", "سودے", "خرید", "فروخت", "بیع", "لین دین", "قرض", "معاملہ", "ناپ", "تول"],
            "honesty": ["دیانت", "حلال", "حرام", "انصاف", "عدل", "امانت", "رضامندی", "گناہ", "ظلم", "کمی", "ناحق"],
        },
        "requires": ["trade", "honesty"],
        "quran": ["2:275", "2:282", "4:29", "83:1-3"],
        "hadith": [],
        "note": "62:10 was here; it says 'seek the bounty of Allah', which is about "
                "provision after prayer, not about honesty in a dealing. Pruned.",
    },
    "women": {
        "label": {"en": "Women", "ur": "عورتوں کے حقوق"},
        "headline": {"en": "Women — equal reward, equal dignity", "ur": "عورتیں — برابر اجر، برابر عزت"},
        "claims": {
            "women": ["عورت", "عورتیں", "عورتوں", "خواتین", "لڑکی"],
            "dignity": ["اجر", "اجر عظیم", "عزت", "بھلائی", "رحم", "دوست", "صلہ", "برابر", "حقوق", "بخشش"],
        },
        "requires": ["women", "dignity"],
        "quran": ["33:35", "16:97", "4:19", "9:71"],
        "hadith": [],
        "note": "33:35 names men and women in parallel for every spiritual rank. 4:1 "
                "was here; it is about creation and kinship, and its own words do not "
                "carry the 'equal reward' claim. Pruned.",
    },
    "parents": {
        "label": {"en": "Parents", "ur": "والدین"},
        "headline": {"en": "Parents — kindness in their old age", "ur": "والدین — بڑھاپے میں حسنِ سلوک"},
        "claims": {
            "parents": ["ماں باپ", "والدین", "والد", "ماں", "باپ", "ابو", "امی"],
            "kindness": ["بھلائی", "احسان", "سلوک", "ادب", "رحمت", "رحم", "دعا", "شکر", "ساتھ دینا", "جھکے", "بڑھاپے"],
        },
        "requires": ["parents", "kindness"],
        "quran": ["17:23-24", "31:14-15", "46:15"],
        "hadith": [],
        "note": "All three verses say 'maan baap' or 'walidain' in their own words and "
                "name the kindness asked for.",
    },
    "knowledge": {
        "label": {"en": "Knowledge", "ur": "علم"},
        "headline": {"en": "Knowledge — read, and ask for more", "ur": "علم — پڑھو، اور مانگتے رہو"},
        "claims": {
            "knowledge": ["علم", "جاننا", "پڑھ", "پڑھو", "سیکھ", "سکھایا", "سکھائیں", "سکھائے", "حکمت",
                          "قلم", "نصیحت", "عقلمند", "دانا", "سکھاتا", "معلوم"],
        },
        "requires": ["knowledge"],
        "quran": ["96:1-5", "20:114", "39:9", "58:11"],
        # ibnmajah:224 was here, and was PUBLISHED. It is graded Very Da'if by
        # al-Albani, Abd al-Baqi and al-Arna'ut (the version with the "necklace
        # around the neck of swine" addition). Removed 2026-10-11 when the
        # authenticity gate (islamic/verify.py) started reading the grades.
        # tirmidhi:2646 replaces it: Sahih per Ahmad Shakir and al-Albani, and
        # Zubair Ali Zai notes it is also in Sahih Muslim.
        "hadith": ["tirmidhi:2646"],
        "note": "96:1-5 is 'iqra'; 20:114 is the du'a for more knowledge. The previous "
                "headline claimed 'a path that never ends', which none of these verses "
                "say - the check cannot see a metaphor, so the headline was made literal.",
    },
    "prayer": {
        "label": {"en": "Prayer & du'a", "ur": "دعا"},
        "headline": {"en": "Du'a — turning to Him at every moment", "ur": "دعا — ہر لمحے اُسی کی طرف رجوع"},
        "claims": {
            "dua": ["دعا", "دعائیں", "مانگا", "مانگتے", "پکارتا", "پکارنے", "پکارنے والا", "قبول",
                    "عبادت", "رجوع", "عاجزی", "خوف"],
        },
        "requires": ["dua"],
        "quran": ["2:186", "40:60", "7:55-56", "2:201"],
        "hadith": [],
        "note": "The word du'a itself appears in every one of these four.",
    },
    "justice": {
        "label": {"en": "Justice", "ur": "انصاف"},
        "headline": {"en": "Justice — the wronged will be heard", "ur": "انصاف — مظلوم کی آواز بھی سنی جائے گی"},
        "claims": {
            "wronged": ["مظلوم", "کمزور", "بےکس", "ناحق", "لڑکی", "ظلم", "ناانصافی", "یتیم"],
            "accounted": ["پوچھا", "پوچھے", "سوال", "حساب", "گناہ", "جرم", "بدلہ", "فیصلہ"],
        },
        "requires": ["wronged", "accounted"],
        "quran": ["81:8-9"],
        "hadith": [],
        "note": "This topic exists because of a review: 81:8 ('when the girl buried "
                "alive is asked') was labelled 'Daughters - a blessing'. It is about a "
                "crime and an accounting, so it lives here instead. The topic is a "
                "home for it, not a relabelling - the headline says what the verse says. "
                "4:135 and 16:90 were tried here and moved out: they command justice, "
                "they do not name anyone wronged, and the check said so.",
    },
    "fairness": {
        "label": {"en": "Fairness", "ur": "عدل و انصاف"},
        "headline": {"en": "Fairness — stand for justice, even against yourself",
                     "ur": "انصاف — حق پر ڈٹو، اپنے خلاف بھی"},
        "claims": {
            "fair": ["انصاف", "عدل", "حق", "گواہی", "سچی", "احسان", "قائم"],
        },
        "requires": ["fair"],
        "quran": ["4:135", "16:90"],
        "hadith": [],
        "note": "Split out from 'justice' after the audit: these two command justice "
                "without naming a victim, so they could not honestly carry a headline "
                "about the wronged being heard. 4:135's own words are the source of the "
                "'even against yourself' half - it names your own self, parents and kin.",
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
