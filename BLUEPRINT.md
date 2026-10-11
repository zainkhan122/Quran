# Blueprint — how the Islamic Video Studio is put together

A vertical video about a verse of the Qur'an or a hadith has to solve four
problems at once: the text must be **authentic**, the Arabic must be **in time
with a real recitation**, the frame must be **legible on a phone**, and the whole
thing must run **free, without a GPU**. This document is how each one is closed.

---

## 1 · The trust boundary

`islamic/sources.py` is the only module allowed to produce text, and it only ever
fetches. It exposes one dataclass and one hard gate:

```python
VerbatimItem(kind, arabic, urdu, english, source, reference, source_ar, grade, topic)
    .validate()   # raises ContentError unless the item is publishable
```

`validate()` refuses to render when a citation is missing, when there is no text
in any language, when an `arabic`/`urdu` field contains no Arabic script at all,
or when a hadith names a collection outside `TRUSTED_COLLECTIONS`. It is
deliberately strict about the one failure this project exists to prevent:
invented or garbled sacred text reaching a frame.

Why this matters more than it looks: a language model asked for "the hadith about
intention" will produce a number, a chain and a wording that sound entirely
plausible and may be wrong. Removing the ability to author text is the only
reliable fix. Everything downstream can therefore assume its input is real.

**Sources.** Qur'an from `api.quran.com` v4 (Uthmani + Jalandhry Urdu + Sahih
English, plus per-word timings and the recitation file). Hadith from
`fawazahmed0/hadith-api` over jsDelivr, ten collections, eleven languages.
Recitation audio from `verses.quran.com`. Fonts from `google/fonts`.

**Isnad.** Hadith are stored and displayed with their chain of narration. An
earlier version of this pipeline trimmed the isnad to leave the "clean" part, and
it was wrong: in Urdu, `"نے کہا"` means *"he said that [the next narrator]…"*, so a
trimmer cuts mid-chain and presents a narrator's name as the Prophet's words. The
trimmer is gone. `has_isnad()` only detects, and the detection decides one thing —
whether to narrate the hadith in a synthetic voice, which is refused.

**Grading.** Where a collection carries a range of grades (Ibn Majah, Abu Dawud),
the frame says so. A hadith shown without its grade invites the reader to assume
the strongest one.

---

## 2 · Word-by-word, with real timings

The design goal was Arabic appearing word by word in step with the recitation.
Three routes were possible; only one is honest.

| Route | Verdict |
|---|---|
| Concatenate the API's per-word `wbw/*.mp3` clips | **fails** — clips are cut tight, totalling 0.74× the ayah (all pauses removed), and the last word's clip 404s |
| Forced alignment (Whisper + DTW) | works, but ships a model and guesses; unnecessary |
| `audio.segments` from the publisher | **used** — exact `[word_from, word_to, start_ms, end_ms]` rows for the very MP3 we play |

`islamic/timings.py` fetches that array and zips it to the word list; the frame
loop lights exactly the word whose window contains the current timestamp. No
correlation, no model, no approximation — and the same numbers drive the audio
timeline, so picture and sound cannot drift apart.

`verse.words` ends with the ayah-number marker, which has no audio; the segment
indices are 0-based into that array, so the marker is dropped explicitly rather
than by luck.

---

## 3 · The frame

`islamic/studio.py`. Canvas 1080×1920 at 30 fps. Palette: deep teal-green ground,
gold ornament, ivory text.

**Order of operations, per video**

```
gradient ground
  → girih lattice tiled at 16 %
  → topic motif, converted to gold ink, at 42 %     (assets/motifs/<topic>.png)
  → islimi medallion at 18 %
  → vignette + double hairline border
  → soft scrim behind the body text
  → topic header (English line, rule, Urdu line)
  → body  (phase 1 Arabic / phase 2 meaning)
  → citation block at the foot
```

**Ornament as ink, not as a pasted image.** The motif files are gold strokes on
their own dark ground. Pasting them as images leaves a visible rectangle where
their background meets ours — an early build showed exactly that seam. So each
one is resized, converted to a luminance mask (anything above the ground colour
becomes ink), re-coloured to the palette, and alpha-composited. Only the lines
land on the frame.

**A scrim keeps the brief honest.** The user asked for art behind the text; art
competing with the text is a legibility bug. A heavily blurred dark rounded
rectangle pushes the artwork back exactly where type sits and leaves it visible
either side.

**Measured ink-centring.** Text blocks are centred on the bounding box of the
glyphs actually drawn, not on the layout box. Amiri's stacked diacritics make
those two differ by enough to make a card look top-heavy — the first version did.

**The topic cannot overflow.** `fit_lines()` walks the size down until the string
fits one line (`topic`) or a line budget, so a longer headline loses size and
never structure. Two lines total: English, then Urdu. The Urdu is drawn in Noto
Nastaliq, which needs ≈2.6× line height, not 1.4×.

**Citations are set at 36 px on a 1080-wide frame** — deliberately larger than
looks necessary on a desktop monitor, because the target is a phone.

**Two body modes, one renderer.** Qur'an ⇒ word-by-word reveal. Hadith ⇒ the
Arabic is set whole and held, because no per-word audio exists for it; the Urdu
narration plays underneath while it is on screen, then the meaning takes over.

**Highlight behaviour.** Words not yet recited sit in a dim sage tone; the word
being recited is drawn with a soft gold halo; words already recited stay gold.
The halo is painted as a small RGBA patch around that one word — no full-canvas
layer per frame, and no reliance on `ImageDraw`'s private `.im`, which Pillow 12
removed.

**Speed.** Both frame bases are composited once. Each frame copies one and
repaints only the words whose state changed, then writes raw RGB straight into
ffmpeg's stdin. No PNGs touch the disk; ~2.5 minutes for a 50-second video on two
cores. ffmpeg's exit code is checked — an earlier version silently shipped a
truncated file when an output was removed mid-render.

---

## 4 · The topic system

`islamic/topics.py` holds each topic's `label` (short, for filenames), `headline`
(what is actually set on screen — explanatory, not a single word, and short
enough to fit one line per language) and its reference list.

That file contains **references only, never sacred text**. A mistake in it can
put a verse in the wrong video; it can never corrupt the verse.

`tools/motifs.py` is the art registry: one written prompt per topic, encoding the
rules — geometric and botanical only, never figurative; never anything that could
read as a letter, since a stray glyph beside real Qur'anic text is a serious
error; matched stroke weight so a new motif drops into the set.

---

## 5 · Build → web → publish

```
output/video/            git-ignored build folder
  <name>.mp4
  <name>.build.json      timing, sizes, reciter, pipeline version
  videos.json            { "<name>.mp4": "<reference>" }     filename -> citation
  sources.json           every reference built, with its verbatim text
        │
        │  python tools/publish.py
        ▼
web/video/               committed
  <name>.mp4  posters/<name>.jpg  manifest.json
```

The filename alone cannot be trusted to carry the reference (`quran-30-21.mp4`
is indistinguishable from a genuinely hyphenated reference), so the mapping is
written at build time. `publish.py` is the only thing that writes to `web/`: it
rebuilds the manifest from each build's own JSON, and prunes anything the
manifest no longer references, so the site can never link to a missing file.

---

## 6 · Two environments, one codebase

Nothing installed by apt or pip survives in this sandbox — only files under
`/home/user`. `setup.sh` is therefore part of the build, not a convenience: it
reinstalls ffmpeg and the wheels, then runs `tools/fetch_fonts.py`, which
*verifies* every font (a previous build shipped three GitHub 404 HTML pages
named `.ttf`, which only surfaced much later as "unknown file format" at render
time).

The same code runs on GitHub Actions and publishes to Pages: the renderer is pure
Pillow + ffmpeg, single-threaded-ish by design, and the only network calls are
the verbatim fetches. No GPU, no paid API, no model downloads required for the
Qur'an path.

**Considered and not adopted:** HyperFrames (HTML/CSS → deterministic MP4) is a
strong tool and was suggested for the polish pass, but it requires Node ≥ 22
(this environment has 20) plus Chromium. The renderer needed here is
word-timestamped and composited rather than seek-driven HTML animation, so the
Pillow path was kept — it renders in minutes, needs no browser, and keeps the
whole pipeline runnable on the free tier.

---

## 7 · Open items

* Motifs for `parents` still fall back to the generic islimi layer (7 of 8 drawn).
* Topic reference lists in `topics.py` are seeds and want a human check before
  they are treated as authoritative collections.
* Language: the Urdu translation is published text (Jalandhry) and is read by
  TTS; a human voice would be better and is a naming/consent problem, not a
  technical one.

---

## 8 · Operating doctrine

The discipline below is adopted from `zainkhan122/yt-tts · reels-studio`, a
sibling system that had already solved the problems this one was re-learning:
sessions that time out, a 2 GB sandbox, state that has to survive a reset, and a
render that has to happen with no local machine. Each rule is here because it
fixed something, not because it sounds good.

### Adopted

| Practice | What it fixes here |
|---|---|
| **One phase per session**, in a table with a dated log | Long sessions have timed out. A phase is small enough to finish, verify and commit. |
| **`setup.sh` as the first command**, idempotent, with a `--check` fast path | Nothing installed survives a reset. Re-entry has to be one command, not a memory test. |
| **At most one heavy job at a time** | Two memory-heavy jobs in 2 GB is how ffmpeg dies silently and ships a truncated video. |
| **State written to the repo, not the conversation** — a one-screen `STATE.md` plus a phase log | The repo is the memory. A session that has to be re-derived from chat is a session already half lost. |
| **Retrieval over reading** — scripts that print answers instead of files pasted into the transcript | Reading to reason is what fills a context window and ends a session early. Read in full only to edit. |
| **Cloud renders on free GitHub runners** (4 vCPU / 16 GB on a public repo) | The 2 GB sandbox is the binding constraint on quality and on what can run at all. Renders there are 6–17× faster. |
| **QA gates before publish**, and a publish step separate from the render step | A render that has not passed a check is a draft. Publishing is its own decision. |
| **Receipts in git** — what was published, when, with what hash | Prevents the one unrecoverable mistake: re-uploading or overwriting a live asset. |
| **Secrets in Actions secrets, a vault outside the workspace, nothing in the repo** | The workspace is snapshotted and shareable. Credentials must never be either. |
| **A storage budget with pruning after verification** | Snapshots are capped (~128 MB); build directories are regenerable and must stay out of git. |
| **An asset policy written down**: origin, licence basis and digest for everything that reaches a frame | "Attribution" is not a licence. Every visual needs a recorded basis. |

### Not adopted, and why

* **Their content model.** reels-studio is an AI-tools shorts factory; the rules
  that make it work (hook, retention, trend radar) are orthogonal to the constraint
  that governs this project, which is that sacred text is fetched verbatim and
  never authored.
* **Their agent-critic layers and model comparison lab.** Valuable for judging a
  generated script; this pipeline has no generated script to judge. The correctness
  gates here are deterministic and cheap: citation present, translation verbatim,
  isnad not narrated, recitation real.
* **Their publishing providers (Buffer, Meta, YouTube API).** Free and useful, but
  they are a delivery question and belong to a later phase, not to the renderer.

### Consequences for this repo

Four documents, each with one job — no more:

| Document | Job |
|---|---|
| `README.md` | What this is and how to run it |
| `PHASES.md` | The plan, the session rules, the phase log |
| `STATE.md` | The one-screen resume capsule |
| `BLUEPRINT.md` | How it is built, and the doctrine above |

`ASSESSMENT.md` is kept as a historical record of the TTS survey and the
"reading, not reciting" correction; it is not part of the operating set.
