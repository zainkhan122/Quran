# Sources and verification

Where every word on a video comes from, and how the pipeline checks it before
a single frame is rendered. The rule behind all of it: **this project authors no
sacred text.** Everything is fetched from a citable dataset at build time, with
its reference, and then checked.

## Where the content comes from

| Content | Source | What we take |
|---|---|---|
| Qur'an, Arabic | **api.alquran.cloud**, edition `quran-uthmani` (Tanzil Uthmani text) | the ayah |
| Qur'an, check text | **api.quran.com** v4, `text_uthmani` (Quran Foundation) | used only to cross-check the Arabic |
| Qur'an, Urdu | alquran.cloud `ur.jalandhry`: Fateh Muhammad Jalandhry | translation shown on the card |
| Qur'an, English | alquran.cloud `en.sahih`: Saheeh International | translation shown and narrated |
| Recitation + word timings | **api.quran.com** v4 recitation 7: Mishary Rashid Alafasy, with per-word `segments` | a real qari, never TTS; the timings drive word-by-word highlighting |
| Hadith (Arabic, Urdu, English **and grades**) | **fawazahmed0/hadith-api** via jsDelivr | text plus the named graders' verdicts |
| Du'as | **The Qur'an's own du'as** (the "Rabbana" verses, e.g. 2:201, 25:74, 20:114), sourced as Qur'an refs. **Prophetic du'as** come from the hadith collections, sourced as hadith refs. *Hisn al-Muslim* is used only as an **index** to find them: every du'a goes to video under its primary-collection reference and through the same grade gate. A du'a never goes out on the authority of a du'a book alone. | |
| Topics | `islamic/topics.py`: each topic declares the words it **claims** (in Urdu) and which claims it **requires**. A topic is a label we write; the gate makes sure the fetched text actually says it. | headline, motif, claim words |

Hadith collections accepted at all: Bukhari, Muslim, Abu Dawud, Tirmidhi,
Ibn Majah, Nasa'i, Muwatta Malik. Being in one of these is **necessary, not
sufficient.** See the grade gate below.

## How it is verified: four gates, all fail-closed

Each gate stops the render. None of them has a skip flag.

**1. Authenticity gate** (`islamic/verify.py`), run first: in CI before any
runner is spent, and again inside every render.

* **Qur'an, two independent sources must agree.** The Arabic from
  alquran.cloud is compared with quran.com's text. The two editions differ in
  orthographic convention (tatweel, how hamza is written, small alef), so both
  are reduced to the letter skeleton first, and the skeletons must then be
  **identical**. Tested: it caught **75 of 75** single-letter substitutions
  planted in 30:21. All 31 Qur'an refs in the catalogue pass.
* **Hadith, the graders must agree it is acceptable.** Bukhari and Muslim are
  accepted (scholarly consensus). For every other collection, at least one named
  grader (al-Albani, Ahmad Shakir, Shu'ayb al-Arna'ut, Zubair Ali Zai, ...) must
  call the narration **sahih or hasan**, and **none** may call it da'if, munkar,
  shadh, mawdu' or batil. A **disputed** narration is refused, not averaged. A
  grade wording the gate does not recognise is a refusal until a person reads
  it. No grading at all means refused.
* The card prints the verdict and who gave it, e.g.
  *"Sahih - graded by Ahmad Shakir, Al-Albani, Zubair Zai"*.

**2. Relevance gate** (`tools/check_relevance.py`). The topic's claim words
must occur in the fetched text itself. This is the gate that rejected
`daughters` for 81:8. It also covers a trap the grade gate cannot see:
**numbering.** Collections have several numbering schemes, and the dataset's
`muslim:2699` is *not* the famous Muslim 2699. A correct grade attached to the
wrong hadith cannot also pass a check on what that hadith says.

**3. Render gate** (`tools/check_video.py`): duration, resolution, a
recitation track present for every Qur'an clip, loudness in range, and a build
record that names its reference, source, grade and narration voice.

**4. Publication gate** (`tools/publish.py`): the render gate again at the
last step, plus a manifest check that every clip names the Release its media
lives in.

## What the gates found on their first run (2026-10-11)

| ref | verdict | action |
|---|---|---|
| `ibnmajah:224` "seeking knowledge is a duty... necklace... swine" | **Very Da'if**: al-Albani, Abd al-Baqi, al-Arna'ut; Da'if: Zubair Ali Zai | **it was published; now withdrawn.** Replaced by `tirmidhi:2646` (Sahih) |
| `tirmidhi:1912` | Da'if (Shakir, al-Albani, Zai) | removed from the catalogue |
| `tirmidhi:1916` | disputed: Da'if ×2, Hasan ×2 | removed (disputed means refused) |
| all 31 Qur'an refs | two sources agree | pass |

The old pipeline accepted `ibnmajah:224` because it checked only whether the
*collection* was trusted. Then it printed "See a scholar, this collection
contains a range of grades" on the card. The narration's own grades were in
the payload it had already downloaded. Nothing read them.

## What this does not replace

A scholar. The gates enforce a stated policy mechanically; they do not issue
rulings. The policy is deliberately conservative and will refuse some
narrations a scholar would accept. That is the right trade: a false refusal
costs one video, while a false acceptance attributes a weak report to the
Prophet (peace be upon him). For anything that will be published widely, a
qualified person reviewing the weekly plan is still the standard to aim for.
