# State — 2026-10-11 (Phases 0-4c done; PUSHED; cloud dispatch is the next thing)

Resume capsule. One screen. **A new session starts by reading `RESUME.md`** and
running `bash tools/resume.sh`; this file is what that script reports from.
If this file and the repo disagree, the repo wins — fix this file.

## ⚠ One commit is local-only (2026-10-11)

`38564e5` (**was `6c5eadf`** — the history was rewritten again to drop 39.1 MB
of retired renders, see `docs/CLEANUP-LOG.md`) — the approved voice, all three
clips re-rendered — is **committed but not pushed.** The remote is still at
`7134eeb`, which is the pre-rewrite tip, so this **needs `--force-with-lease`**,
not a plain push. The sandbox rolled back mid-session and took `/tmp/.ght` with it
(by design: the token never lives inside `/home/user`, so a snapshot can never
leak it). `.git/config` went too; it was restored from
`setup/git-config.template`.

To finish the push, paste the token again and:

```bash
printf '%s' '<token>' > /tmp/.ght && chmod 600 /tmp/.ght
cd /home/user/naat-ai && TOK=$(cat /tmp/.ght) \
  && git remote set-url origin "https://x-access-token:${TOK}@github.com/zainkhan122/Quran.git" \
  && git push --force-with-lease origin main \
  && git remote set-url origin "https://github.com/zainkhan122/Quran.git"
```

Everything else in this file is already true of `6c5eadf`.

## Where things stand

* **Everything is pushed.** `origin/main` is level with the local branch. The
  remote is the source of truth — the only storage that has never lost a commit.
* **Phases 0-4c are complete.** The studio renders; `tools/check_video.py`
  gates the *file*; `tools/check_relevance.py` gates the *pairing*; and every
  design instruction the owner has given is pinned by a test in
  `tests/test_design.py` with the reason written next to it.
* **The published set is current and now narrated by the approved voice** — re-rendered in this phase, so it carries
  the compact header, the bold ayah, both translation halves and English
  narration.
* **Cloud dispatch is the outstanding step.** The workflow is built and
  rehearsed and has never been run.

## What changed in Phase 4c

Two instructions, each answered with a measurement rather than an opinion.

| asked for | done how | pinned by |
|---|---|---|
| "heading is taking almost 40% of space... needs to be compact so that main content takes main space" | a hard `HEADER_BUDGET` (12.5% of the frame) replaces "whatever it takes to fit"; type is placed by measured ink, not the font's nominal box | `TestTheHeaderStaysCompact` (5 tests) |
| "TTS will be in English, not in Urdu. Translation will be in Urdu and English both while TTS will read English" | `--narrate` defaults to `english`; both translations are captioned always; default voice is `en_free` (LibriTTS-R, CC BY 4.0) | `test_the_voice_reads_english_by_default` |
| (found while checking the result) the honouring of the Prophet drew as an empty box | `for_display()` spells out ligatures the fonts cannot draw; a `.notdef` scan runs over every shipped field | `TestNoMissingGlyphs` |

## The card, measured — `python3 tools/layout_report.py`

| clip | header before | header now | body before | body now |
|---|---|---|---|---|
| `quran:81:8` | 12.9% | **10.1%** | 63.2% | **69.8%** |
| `quran:30:21` | 28.4% | **12.8%** | 47.7% | **67.1%** |
| `ibnmajah:224` | 12.4% | **10.2%** | 61.0% | **67.1%** |

Two causes, both measured: the Urdu heading reserved **2.6x** its font size as a
line height while Nastaliq ink is **1.88x** (English 0.97x); and a headline that
just missed the one-line threshold was re-set at the *largest* size on two
lines, doubling the block. `_fit_topic` now searches for the largest size whose
block fits the budget, charging a fixed penalty per extra line so a headline
that only just wraps does not win over a slightly smaller one-line one.

## Voice: APPROVED — Michael (Kokoro am_michael)

The English narration was rejected — *"TTS is very bad for English. use male
sound."* — and both halves of that turned out to be measured, one of them our
mistake.

**The engine was Piper** (`rhasspy/piper`, a 2023 VITS model). The voice we
shipped as the English default, `en_US-libritts_r-medium` speaker 60, was
catalogued **male** and **measures 248-250 Hz — the female range.** The owner
heard a defect we had recorded as a fact, and the catalogue was wrong.

**The owner auditioned six male voices and chose "Michael."**
`docs/samples/voice-audition-en.mp3` is the pack that was approved and
`tools/voice_audition.py` is the tool that built it. Kokoro-82M: Apache-2.0,
353 MB, RTF 0.86, 13 male voices. Every candidate's pace and pitch were
measured by an instrument validated against synthetic tones
(`--check-pitch`), because the first measurement attempt disagreed with itself
by two octaves and had to be thrown away.

| # | voice | licence | wpm | F0 | |
|---|---|---|---|---|---|
| 1 | piper en_free | CC-BY-4.0 | 180 | **248 Hz** | rejected — female range |
| **2** | **kokoro am_michael** | **Apache-2.0** | **177** | **117 Hz** | **APPROVED** |
| 3 | kokoro am_onyx | Apache-2.0 | 206 | 88 Hz | kept available |
| 4 | kokoro am_fenrir | Apache-2.0 | 186 | 141 Hz | kept available |
| 5 | kokoro bm_george | Apache-2.0 | 176 | 132 Hz | kept available |
| 6 | kokoro bm_lewis | Apache-2.0 | 183 | 91 Hz | kept available |

`en_michael` is the default English voice; the other four Kokoro males stay in
the catalogue, so switching is one flag (`--engine en_onyx`). Measured on the
narration alone, all three clips read at **113 Hz** — the same voice, every
time.

Two backends now sit behind one key space (`islamic/voice.py` `make_voice`):
Piper for Urdu, Kokoro for English. `setup.sh` installs and fetches both, and
the render workflow caches `~/.cache/kokoro` beside `~/.cache/urdu-voice`.

## Narration## Narration

* **English by default**, card carries **both** translations (`--no-english` is
  the escape hatch). `--narrate urdu` still exists but is no longer the path.
* Default voice `en_free` = LibriTTS-R, **CC BY 4.0** — chosen because English is
  now the voice of the channel, so the default must be publishable. `en`
  (lessac) sounds better but is a Blizzard research licence; it stays as the
  A/B voice and is flagged `test_only`.
* **Delivery: 0.0 pauses/min on all three clips** (narration-only window),
  against the study's creator median of 1.5 and line-by-line synthesis at 19.2.
* The hadith gained narration: its isnad used to suppress the Urdu voice.

## The Urdu TTS question is CLOSED

Not by an engine change — the Urdu voice is simply no longer used. Urdu stays on
the card as text. That retires the "get a native Urdu speaker to judge the
voice" item; `docs/samples/voice-samples.mp3` is kept only as the record of that
work, in case `--narrate urdu` is ever revisited.

## Run these before you commit

```bash
bash tools/resume.sh                           # restore + verify + report, ~1 min
python3 -m unittest discover -s tests          # 115 tests, ~40 s, stdlib, offline
python3 tools/layout_report.py                 # the card's vertical budget
python3 tools/check_relevance.py --audit       # topic vs its own refs (network)
python3 tools/cleanup.py                       # both budgets, changes nothing
python3 tools/publish.py                       # gate every clip, then write the site
```

## The published set

| reference | seconds | size | headline on the frame |
|---|---|---|---|
| `quran:81:8` | 11.20 | 1.16 MB | Justice — the wronged will be heard |
| `quran:30:21` | 52.57 | 5.52 MB | Marriage — love and mercy between spouses |
| `ibnmajah:224` | 44.97 | 4.02 MB | Knowledge — read, and ask for more |

Loudness −14.1 / −13.7 / −15.1 LUFS PASS; relevance `--library --offline` PASS.
Each has a `.build.json` that names the voice, the language and the spoken
seconds.

## Next session, in order

1. `bash tools/resume.sh` — it does the whole of the orientation for you.
2. **Dispatch one clip** (`tools/cloud.sh render quran-81-8`) and compare the
   runner's output against the local render — duration, size and loudness.
   The workflow now inherits the English narration default.
3. If it holds, dispatch the full library and confirm the Release and the site
   commit. Then mark Phase 2 done.
4. Phase 5: grow `library.json` from the 34 validated refs (~10 at a time,
   `--audit` after each batch) and add `--daily N` rotation for the 3-5/day
   cadence.

## Open items, honestly

* **The relevance gate cannot certify a translation.** It checks that the words
  the headline claims occur in the text we display. It cannot read context and
  it cannot see a metaphor. It is a tripwire, not a review.
* **A short verse leaves a visible gap in phase 2.** `quran:81:8` is one line of
  Urdu and two of English inside equal halves, so there is empty frame between
  them. The halves are the owner's spec; filling the space would mean changing
  it. Worth asking before changing.
* **Every re-render leaves the previous mp4 in history** (~11 MB per cycle).
  This was squeezed twice on 2026-10-11 — see `docs/CLEANUP-LOG.md` for both
  procedures and the trap that makes `git gc` useless for it (a
  `refs/remotes/origin/*` ref holding the old commits alive). Headroom is
  42.5 MB now; squeeze again when it falls under ~15 MB.
* **The ۱؎ footnote dagger in some hadith texts renders as cryptic marks.** It is
  faithful to the source and the speech path strips it; stripping it from the
  card too is a content decision the owner should make.
* **A weekly cron is not a verified cron.** `cleanup.yml` is scheduled, but
  GitHub disables scheduled workflows after 60 days of repo inactivity and the
  schedule has not been observed to fire. Run it by hand if months have passed.

## Environment (not persisted — restored by `tools/resume.sh`)

```bash
bash setup.sh --check     # ~9 s: ffmpeg, wheels, raqm shaping, fonts, ornament
bash setup.sh             # ~3 min cold: the repair/install path (+ voice weights)
```

Three things never survive a snapshot, each for a reason:

* `.git/config` — a credential path, excluded on purpose;
* `~/.cache` — the voice weights (~60 MB each), refetched by `setup.sh`;
* `/tmp/.ght` — the token, deliberately outside the workspace.

`.git` itself has also been rolled back twice while the working tree survived —
push at every phase boundary.
