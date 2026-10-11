# Islamic Video Studio

Citable short-form Islamic video — Qur'an and hadith — on free, CPU-only
infrastructure. No GPU. No paid API. No cloud bill.

```
python3 -m islamic.produce --ref quran:30:21 --topic marriage
        ──►  output/video/quran-30-21.mp4      1080×1920 · word-synced Arabic · cited
```

## What a finished video contains

A vertical 9:16 film, in two movements:

| | On screen | Audio |
|---|---|---|
| **1 · Arabic** | the ayah, revealed **word by word** in time with the recitation — the word being recited lights gold, the words already recited stay gold | a real qari (Mishra Alafasy) |
| **2 · Meaning** | the Urdu translation, then the English caption | Urdu narration |

Throughout there is a **bold explanatory topic line in English and in Urdu**
(`Marriage — love and mercy between spouses` / `نکاح — میاں بیوی کے درمیان محبت اور رحمت`),
**topic-specific 2D art** held back at low opacity behind the words, and a
**citation block at the foot** in a size you can actually read on a phone.

## The rule that shapes everything

**The pipeline never writes, rewrites or paraphrases sacred text.** Every
character on screen is fetched from a published dataset at build time and shown
with its reference.

| Content | Source |
|---|---|
| Qur'an (Uthmani + Jalandhry Urdu + Sahih English) | `api.quran.com` v4 |
| Per-word recitation timings | `api.quran.com` v4 `audio.segments` |
| Qur'an recitation audio | Mishary Rashid Alafasy via `verses.quran.com` |
| Hadith (10 collections, 11 languages) | `fawazahmed0/hadith-api` via jsDelivr |
| Fonts (OFL) | google/fonts — verified by `tools/fetch_fonts.py` |

A language model that "remembers" a hadith number or wording invents them with
total confidence. Fabricated hadith is a grave matter, so the pipeline removes
that failure mode rather than asking a reviewer to catch it.

**Qur'an is never synthesised.** Quranic Arabic carries tajweed no free TTS
implements; the recitation is always a real qari. TTS is used only for the
published Urdu *translation* — and never inside an isnad (see below).

## Word-by-word sync, without guessing

The audio is real, and so are the timings. `api.quran.com` returns, for the very
recitation file we download, a `segments` array:

```
[[0,1,330,930], [1,2,940,3830], …]      word_from, word_to, start_ms, end_ms
```

That is the publisher's own alignment, so no forced aligner, no Whisper model and
no signal correlation is involved. The two tempting shortcuts both fail:
the per-word `wbw/*.mp3` clips are cut tight and are 0.74× the length of the full
ayah (every inter-word pause has been removed), and the clip the API advertises
for the last word does not exist.

## Layout is measured, not eyeballed

`islamic/studio.py` renders every frame itself:

* **ink-centring** — text blocks are centred on the bounding box of the glyphs
  actually drawn, not on the layout box. With Amiri's stacked diacritics the two
  differ enough to make a card look top-heavy.
* **the topic never overflows** — each line auto-shrinks until it fits one line,
  so a longer headline loses size, not structure.
* **ornament is composited as ink** — motif images are gold-on-dark; they are
  converted to a mask and re-coloured, so only the lines land on the frame and
  no rectangle seam appears. A blurred scrim pushes the art back exactly where
  type sits.
* **frames stream to ffmpeg over stdin** — no intermediate PNGs, ~2.5 minutes for
  a 50 s video on two cores.

Art rules, encoded in the prompts (`tools/motifs.py`): geometric and botanical
only, never figurative; never anything that could read as a letter, because a
stray glyph beside real Qur'anic text is a serious error.

## Quick start

```bash
bash setup.sh --check                          # session start: verify in seconds
bash setup.sh                                  # repair/install path (~3 min cold)
python3 tools/motifs.py                        # which topics have their own art
python3 -m islamic.produce --ref quran:30:21 --topic marriage
python3 -m islamic.produce --ref ibnmajah:224 --topic knowledge
python3 tools/layout_report.py                 # where the vertical space goes
python3 tools/publish.py                       # build folders -> web/video + manifest
python3 -m http.server 8000 --directory web    # the site
```

The voice reads **English** and the card carries **both** translations - that is
the default, so a plain `--ref ... --topic ...` gives you the shippable clip.
`--narrate urdu` and `--no-english` exist but are no longer the path.

The English voice is **Kokoro-82M `am_michael`** (Apache-2.0, 117 Hz), chosen by
the owner from `docs/samples/voice-audition-en.mp3` - a pack built by
`tools/voice_audition.py`. Four other male Kokoro voices are catalogued
(`en_onyx`, `en_fenrir`, `en_george`, `en_lewis`), so changing the voice is one
flag. `en_free` is kept only for the A/B that established it is **not male**:
it measures 248 Hz.

`setup.sh` is not optional: this sandbox keeps only files under `/home/user`, so
ffmpeg, the Python wheels and the fonts all have to be re-asserted each session.
Packages, `/tmp` and every running process are lost on a reset; the repo is the
only memory, which is why state lives in `STATE.md` instead of in the chat.

**Work one phase per session.** `PHASES.md` holds the session rules, the phase
table and the dated log; `STATE.md` is the one-screen resume capsule. Start a
session by reading those two, not the whole document set.

### Topics

`marriage` · `children` · `daughters` · `business` · `women` · `parents` ·
`knowledge` · `prayer` — each with a headline, a short label and a list of
references in `islamic/topics.py`. That file holds **references only**: a mistake
there can mislabel which video a verse lands in, but it can never corrupt the
verse itself.

## Corpus honesty

* Only collections on `TRUSTED_COLLECTIONS` render at all.
* Hadith are stored and shown **with their isnad**. An earlier attempt to strip
  the chain for a cleaner card silently cut mid-chain — in Urdu isnad, `"نے کہا"`
  means "he said that [the next narrator]…", so the trimmer happily presented a
  narrator's name as the hadith. It was removed; `has_isnad()` is now a detector,
  never a trimmer.
* Collections that publish no Urdu edition (Nawawi 40, Qudsi 40, Dehlawi 40)
  raise a content error rather than falling back to English-only silently.
* Where a collection carries a range of grades, the frame says so.

## Repo layout

```
islamic/
  sources.py    verbatim fetch + validate() gate; the trust boundary
  topics.py     topic headlines + reference lists (no sacred text)
  timings.py    per-word timings from api.quran.com audio.segments
  studio.py     the renderer: design system, layout, ornament, frame loop
  produce.py    the CLI that ties it together
  narrate.py    narration in a child process (keeps the box free for ffmpeg)
  english.py    English speech/display prep; the font-coverage substitutions
  kokoro.py     Kokoro-82M: the English narration voice (Apache-2.0)
tools/
  fetch_fonts.py  download + verify OFL fonts (verify by magic bytes, not name)
  motifs.py       the 2D art registry and its prompts
  publish.py      build folders -> web/video + manifest.json + posters, prunes stale
  layout_report.py  the card's vertical budget per clip (header/body/type sizes)
naat/           Urdu TTS (used for translation narration only)
web/            the site: index.html, videos, fonts, posters
assets/         fonts/, textures/, motifs/
PHASES.md       session rules, phase table, dated log       <- read first
STATE.md        one-screen resume capsule                    <- then this
BLUEPRINT.md    architecture and operating doctrine
ASSESSMENT.md   historical TTS survey (not part of the operating set)
```

## Publishing

Builds land in `output/video/` (git-ignored). `tools/publish.py` is the only
thing that writes to `web/`: it copies files, renders a poster frame, rebuilds
`manifest.json` from each build's `videos.json` + `sources.json`, and prunes
anything the manifest no longer references — so the site can never link to a
file that is not there. Pushing the repo deploys the Pages site.

## Licensing

Fonts (Amiri, Noto families) and DejaVu are OFL — safe for commercial use.
Generated motif art is ours. Recitation and translation text come from the
sources above; check each upstream's terms before monetising.

**Standing refusal:** no real person's voice, living or dead, without explicit
written consent.

*(The `naat/` package is the Urdu VITS + tarannum engine, retained because the
video pipeline uses its TTS for translation narration. Naat generation itself is
not a goal of this project.)*
