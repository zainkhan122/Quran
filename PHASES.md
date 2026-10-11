# Phases — one phase per session

**This file is the plan and the log.** Read it first, work one phase, update it last.

## Session rules

Long sessions in this project have timed out and the sandbox resets between
sessions (installed packages, `/tmp` and every process are lost; only files under
`/home/user` survive). These rules exist because of that, not for tidiness.

1. **Start with `bash setup.sh`.** It re-asserts ffmpeg, the Python wheels, the
   fonts and the ornament, and verifies complex-text shaping. Idempotent; ~3 min
   cold, seconds warm. `bash setup.sh --check` verifies without installing.
2. **At most ONE heavy job per session** — one render, or one TTS run. The box has
   2 GB of RAM. Two memory-heavy jobs at once is how ffmpeg gets SIGKILLed with an
   empty stderr and a video silently ships truncated or mute.
3. **Keep the transcript small.** State lives in the repo, not the conversation
   (see *Evidence rules*). Retrieve with a script instead of reading whole files.
4. **Run the suite before committing.** `python3 -m unittest discover -s tests`
   — 104 tests, ~12 s, no dependencies, no network. The gates protect publication,
   so a change to them must be proven, not assumed.
5. **End the session with:** workspace clean, `PHASES.md` status + phase log
   updated, `STATE.md` refreshed, everything committed and pushed.
6. **Never leave a half-edited file.** Re-run the file after each patch; a
   partial edit once left a `NameError` in the manifest builder that only surfaced
   in the next session.

## Phases

| # | Session goal | Deliverable | Status |
|---|---|---|---|
| 0 | **Foundations.** One renderer (two existed), clean tree, phased plan, state capsule, repo pushed | this file, `STATE.md`, single-source renderer, clean tree | ✅ 2026-10-11 |
| 1 | **Make the studio render at all.** Fix the ffmpeg tail-hang; move Urdu TTS into a short-lived process; render the three clips | 3 MP4s + posters + `manifest.json` | ✅ 2026-10-11 |
| 2 | **Cloud render.** Free GitHub runners (4 vCPU / 16 GB) instead of the 2 GB sandbox; outputs to a Release; no secrets needed | `.github/workflows/render.yml` | 🔨 built + rehearsed; needs a token to push and dispatch |
| 3 | **QA gates.** Machine checks that must pass before a video reaches `web/video/` | `tools/check_video.py` (file + correctness gates), wired into `tools/publish.py`, with `tests/` | ✅ 2026-10-11 |
| 4 | **Voice, relevance, cadence.** Replace the CC-BY-NC voice; make the reviewed topic/ayah mismatch a machine check; measure what a 3-5/day library needs | `islamic/voice.py`, `islamic/urdu.py`, `islamic/relevance.py`, `tools/check_relevance.py`, `RESEARCH.md` | ✅ 2026-10-11 |
| 4a | **Flow, and English.** The robotic pauses traced to our own per-line synthesis + flat glue; read the passage in one pass. Add an English voice path and a delivery-measurement instrument | `islamic/voice.py` `say_flow`, `islamic/english.py`, `tools/voice_metrics.py`, `--narrate` | ✅ 2026-10-11 |
| 4b | **Design + robustness.** Ayah weight, stronger reading scrim, equal heading sizes, translation split into equal halves; art for all 10 topics; `tools/resume.sh`, `tools/cleanup.py` + weekly workflow, `RESUME.md` | `islamic/studio.py`, `tools/resume.sh`, `tools/cleanup.py`, `RESUME.md`, `tests/test_design.py` | ✅ 2026-10-11 |
| 4c | **Compact header + the voice speaks English.** Owner: *"heading is taking almost 40% of space... it needs to be compact so that main content takes main space"* and *"TTS will be in English, not in Urdu. Translation will be in Urdu and English both while TTS will read English."* Header given a hard budget (measured 28.4% -> 12.8% worst case, body 47.7% -> 67.1%), type now placed by measured ink instead of a nominal line box, `--narrate` defaults to English with the CC-BY-4.0 voice, both translations always captioned, and a .notdef scan so the card cannot draw a missing glyph | `islamic/studio.py` (`_fit_topic`, `HEADER_BUDGET`), `islamic/english.py` (`for_display`), `islamic/produce.py`, `islamic/voice.py`, `tools/layout_report.py`, `tests/test_design.py`, `tests/test_voice.py` | ✅ 2026-10-11 |
| 4d | **The English voice, by audition.** Owner: *"TTS is very bad for English. use male sound... Get from Free High quality ones and get voice approval from me."* Found the shipped English voice measures **248 Hz** - the female range - despite being catalogued male. Bought in Kokoro-82M (Apache-2.0), measured six male candidates with a validated pitch instrument, built the audition pack, and wired in the approved one (Michael, 117 Hz) behind a two-backend voice factory | `islamic/kokoro.py`, `islamic/voice.py` `make_voice`, `tools/voice_audition.py`, the `voice-approval` release (`voice-audition-en.mp3`), `setup.sh`, `render.yml` | ✅ 2026-10-11 |
| 4e | **Robustness: authenticity gate + media out of git.** Owner: *"make it robust. Clean the temp generated media/videos etc from both repo and workspace."* Added `islamic/verify.py` (Qur'an Arabic must match letter for letter across alquran.cloud and quran.com; hadith must be graded sahih/hasan with no grader dissenting), and it found that the **published `ibnmajah:224` is Very Da'if**. Withdrew it and replaced it with `tirmidhi:2646` (Sahih). Media moved to GitHub Releases, Pages deploys from an artifact, every mp4/mp3/jpg purged from history | `islamic/verify.py`, `SOURCES.md`, `tools/fetch_media.py`, `.github/workflows/pages.yml`, `render.yml`, `cleanup.yml`, `tools/cloud.sh` | ✅ 2026-10-11 |
| 5 | **Coverage.** `parents` motif (8th of 8), grow `library.json` from the 34 validated refs, add `--daily N` rotation, render the whole library | clips for every topic | |
| 5b | optional: regenerate `assets/motifs/` procedurally from the prompts in `tools/motifs.py`. The earlier geometric generator was retired in Phase 0 as unused duplication — the committed PNG set is the source of truth, so regeneration needs a spec first | | |
| 6 | **Publishing.** Site polish; optional scheduled render + release; a receipt journal so nothing is ever re-uploaded | | |
| 7 | optional: long-form cuts, landscape variants, an analytics loop (views → topic picks) | | |

### Phase 4d outcome — the voice the owner approved

*"TTS is very bad for English. use male sound. Which TTS engine you are using???
Get from Free High quality ones and get voice approval from me."*

**The engine was Piper** (`rhasspy/piper`, a 2023 VITS model) reading
`en_US-libritts_r-medium` speaker 60. That spec was catalogued male. Measured:
**248-250 Hz**, the female range. So the complaint was not a matter of taste,
and it was our catalogue that was wrong - the same class of error as the
third-party listing that once mislabelled Fasih's licence.

The first pitch measurement was wrong too, and it is worth recording how: an
autocorrelation estimator said 256 Hz for a sample a harmonic-product estimator
called 72 Hz. Two octaves apart, so it was thrown away and replaced with an
instrument validated against synthetic tones of known pitch
(`tools/voice_audition.py --check-pitch`, five tones, accurate to ~1 Hz).

**Candidates from Kokoro-82M** - the current generation of small open TTS, and
Apache-2.0 for the model *and* the voicepack:

    engine / voice        licence     download  size    RTF   F0
    piper libritts_r      CC-BY-4.0     63 MB   63 MB  0.15  248 Hz  rejected
    kokoro am_michael     Apache-2.0   353 MB  353 MB  0.86  117 Hz  APPROVED
    kokoro am_onyx        Apache-2.0   353 MB  353 MB  0.86   88 Hz
    kokoro am_fenrir      Apache-2.0   353 MB  353 MB  0.86  141 Hz
    kokoro bm_george      Apache-2.0   353 MB  353 MB  0.86  132 Hz
    kokoro bm_lewis       Apache-2.0   353 MB  353 MB  0.86   91 Hz

RTF 0.86 is five times slower than Piper and still far inside budget, because
narration already runs in a child process: the 353 MB graph is loaded, used and
dropped before ffmpeg starts. the `voice-approval` release (`voice-audition-en.mp3`) (91 s) plays
the real 30:21 translation through all six, each announcing itself.

**The owner picked #2, Michael.** It is `DEFAULT_EN_VOICE`; all three clips were
re-rendered and now measure **113 Hz** on the narration alone. The other four
stay reachable by flag. Two backends now sit behind one key space
(`make_voice`), `setup.sh` installs and fetches both, and the workflow caches
`~/.cache/kokoro` (353 MB) beside `~/.cache/urdu-voice`.

The catalogue now carries `measured_f0_hz` for every voice it can, and a test
fails if a voice's declared gender contradicts its measured pitch - so this
particular mislabelling cannot happen twice.

### Phase 4c outcome — the header is a label again, and the voice is English

Two instructions, one measurement each.

**"Heading is taking almost 40% of space."** It was true of the clip that was on
screen: `quran:30:21` had a header plate **28.4%** of the frame and **32.9%** of
the frame went by before the body began - on a phone, a third of the screen.
`tools/layout_report.py` (new) prints the whole vertical budget per clip, and
found two causes:

* The Urdu heading reserved a line height of **2.6x** the font size. Nastaliq ink
  actually measures **1.88x**, English **0.97x** - so nearly a third of the
  header block was air. Type is now placed by the ink it really puts down
  (`_ink_h`, `_mm_ink_offset`), not by the font's nominal box.
* A headline that just missed the one-line threshold was re-set at the *largest*
  size on two lines, roughly doubling the block. `_fit_topic` now searches for
  the size that fits a **budget** (`HEADER_BUDGET`, 12.5% of the frame), prefers
  fewer lines with a fixed penalty per extra line, and accepts one common size
  for both languages.

| clip | header before | header now | body before | body now |
|---|---|---|---|---|
| `quran:81:8` | 12.9% | **10.1%** | 63.2% | **69.8%** |
| `quran:30:21` | 28.4% | **12.8%** | 47.7% | **67.1%** |
| `ibnmajah:224` | 12.4% | **10.2%** | 61.0% | **67.1%** |

The verse grew with it: 30:21's ayah went 96 -> 108px and its translation
38 -> 48px (Urdu) / 44 -> 54px (English).

**"TTS will be in English, not in Urdu."** `--narrate` now defaults to English
and the card always carries both translations (`--no-english` is the escape
hatch). The default English voice is `en_free` - LibriTTS-R, **CC BY 4.0** -
not lessac, whose licence is a Blizzard research grant: English is now the
voice of the channel, so the default had to be one we could publish. Lessac
stays reachable as `--engine en` for an A/B and remains flagged `test_only`.

The hadith gained narration as a result (its isnad had suppressed the Urdu
voice), and the honouring of the Prophet is now spoken and drawn: U+FDFA has no
glyph in DejaVu, so the card had been drawing an empty box mid-sentence. A
`.notdef` scan over every field of every shipped reference now runs in `tests/`.

Measured on the narration alone: **0.0 pauses/min** on all three clips, against
the study's creator median of 1.5.

### Phase 1 outcome — both defects closed, with the measurement

**1. The ffmpeg tail-hang — root cause found and proven.** The audio chain ended
in a bare `apad`, which pads with silence indefinitely, and the output relied on
`-shortest`, which cannot propagate EOF from a stdin video feed. ffmpeg therefore
never finished the encode after the last frame had been written. Isolated A/B on a
5 s clip: the shipped form was still running at 32 s and had to be killed; bounding
the pad with `apad=whole_dur=<total>` plus an explicit `-t` finished in **2.6 s**.
`-shortest` is gone.

Two hardening changes went in with it, because a hang must never again cost a whole
session: a deadline that aborts the loop with a real error, and a bounded wait at
the close. ffmpeg's stderr now goes to `output/video/render.log` rather than a pipe
nobody drains — at `-v error` there is nothing to stream, and reading it afterwards
is what turns "it hung" into a message.

**2. The Urdu TTS OOM — fixed by isolation.** `produce.narrate()` now calls
`islamic/narrate.py` as a child process. Measured earlier: dropping the model
returns ~484 MB to the process but not to the OS, and ffmpeg — which needs the bulk
of a 2 GB box — was then killed by a signal that leaves no stderr at all.
The child exits before encoding starts, handing the whole box back.

**3. Legibility defect found by inspecting the output.** The static-Arabic fitter
capped lines at 22, which also capped the type at 64 px: a several-hundred-character
isnad sat in the middle of a 1070 px stage with the reader squinting at it on a
phone. The stage height is now the constraint instead of the line count — 87 px,
a 70 % area increase, and the block fills the stage.

**Also:** the not-yet-recited word colour was a cold steel tone
(`120,146,138`); it now sits in the palette as brass in shadow (`146,124,84`), so
the live word is the brightest thing on the frame.

**Measured results** (all three rendered in this session, one at a time):

| Reference | Duration | Size | Render time | Notes |
|---|---|---|---|---|
| `quran:81:8` | 11.60 s | 1.26 MB | ~15 s | 3 words, word-by-word |
| `quran:30:21` | 52.57 s | 5.98 MB | 71 s | 20 words, word-by-word |
| `ibnmajah:224` | 47.60 s | 4.27 MB | 53 s | isnad shown, no auto-narration |

Word-by-word sync was verified against the publisher's own timings, not by eye:
settled-word ink accumulates monotonically at t≈1.0 s / 1.5 s / 2.9 s, matching the
three word boundaries in `audio.segments`. Averaged programme loudness −14.3 LUFS.

## Phase 2 — what was built, and what is left

Built and rehearsed locally; the only thing not yet done is the part that needs
GitHub credentials (push, then dispatch the run).

| Piece | Purpose | Rehearsed? |
|---|---|---|
| `library.json` | The clip plan: reference -> topic. References only | ✅ `tools/plan_render.py --plan` |
| `tools/plan_render.py` | Turns the plan into a render matrix; refuses a slug/ref mismatch, an unknown topic or a duplicate slug | ✅ incl. the failure paths, and `$GITHUB_OUTPUT` single-line safety |
| `tools/check_video.py` | The hard gate before anything is published | ✅ 3 real clips pass; silent / landscape / truncated fixtures each fail with a reason |
| `tools/publish.py` | A clip is now self-describing (`<slug>.mp4` + `<slug>.build.json`), so parallel runners need no merged index; non-destructive by default | ✅ published from artifacts alone; subset run keeps the rest; `--exact` prunes |
| `.github/workflows/render.yml` | plan -> render matrix -> gate -> publish | ✅ YAML + structure + matrix expansion checked locally |
| `setup.sh` | Runner-safe: PEP 668 fallback, CPU-only torch index | ✅ `--check` |
| `tools/cloud.sh` | push / render / runs / logs / releases in one command; never echoes the token | ✅ incl. the no-token path |

**Why a token is needed at all:** the workflow itself needs none — it uses GitHub's
automatic `GITHUB_TOKEN` for the release and the commit, and no personal access
token may be added to it. A PAT is only needed to push commits from this workspace
and to dispatch a run over the API. The workspace snapshot deliberately excludes
`/tmp`, so the token from the previous session did not survive the sandbox reset;
that is the design working, not a fault.

## Auto-render plan (Phase 2) — no local machine needed

Facts checked 2026-10-11 against GitHub's published runner specs.

| Piece | How it works | Cost |
|---|---|---|
| Render | `render.yml` on `ubuntu-latest` for this **public** repo: 4 vCPU / 16 GB / 14 GB SSD | $0 (unlimited minutes on public repos) |
| Parallelism | one runner per reference via a matrix, `max-parallel` 5 | $0 |
| Output | MP4 + poster committed to a Release, never to git history | $0 |
| Site | GitHub Pages serves `web/`; `manifest.json` points at the Release or the committed file | $0 |
| Secrets | Actions secrets only. Nothing lands in the workspace | $0 |

Renders are 6–17× faster there than in the sandbox, and the 2 GB ceiling that
forces the memory gymnastics above simply disappears. The sandbox keeps doing what
it is good at: authoring, small verification renders, QA and docs.

## Asset policy (what may go into a video)

The correctness rules are the product; this is the production half of them.

* ✅ **Qur'an recitation** from a source whose terms allow it, with the reciter and
  the source recorded in the citation data. Never TTS for scripture.
* ✅ **Published translations** (verbatim, with edition + reference). Currently
  Jalandhry Urdu. Attribution on the frame and in the manifest.
* ✅ **Hadith** only from `TRUSTED_COLLECTIONS`, with the collection's own grade
  shown. A chain of narrators is displayed, never auto-narrated.
* ✅ **Our own generated ornament** — girih lattice, islimi arabesque, arches —
  and fonts under the SIL Open Font License. Licence texts ship in `assets/fonts/`.
* ❌ **No authored or paraphrased sacred text**, by us or by a model. Fetch verbatim
  or do not ship.
* ❌ **No real person's voice** — living or dead — without explicit written consent.
* ❌ **No asset without a recorded origin and licence basis.** Attribution alone is
  not a re-use permission.

## Evidence rules (so a session can resume cheaply)

* **Think in code.** Read, filter and count with a script that prints the answer;
  never paste a file into the conversation to reason over it.
* **State is written, not remembered.** Anything a later session needs goes into
  `STATE.md`, `PHASES.md` or a JSON receipt in `output/` — not into chat.
* **One render transcript, bounded.** Long command output goes to a log file and
  only the exit code and the interesting lines enter the transcript.
* **Verify by re-running the file**, not by reading the diff.

## Phase log

* **Phase 4b ✅ (2026-10-11)** — The four design corrections, and the robustness the
  project had been missing.
  * *Arabic ayah bold*: simulated with a symmetric outline stroke rather than a
    font swap, because the ayah is set in Amiri and Amiri has no bold — swapping
    would change the typeface, which is a bigger change than was asked for.
    Scales with frame width so it does not vanish at 1080 or smear at 4K.
  * *Reading scrim*: the bed behind the body text went from 88/255 to 132/255.
    At 88 the topical art was still competing with the Arabic on a busy frame.
  * *Equal heading sizes*: English and Urdu used to carry different caps (0.053
    and 0.070), which is why the English came out visibly smaller. Both are now
    fitted, then re-set at the smaller result. The first attempt allowed two
    lines by default and orphaned "رحمت" onto a line of its own — worse than the
    size it bought — so single-line wins unless it would fall below a floor, and
    the two-line fallback wraps by *balance* rather than greedily.
  * *Translation halves*: the body is zoned into two equal halves, Urdu over
    English, each block centred in its own half with the gold rule between.
    English used to be capped at 30% of the body while Urdu took 86%, which is
    why it looked small and low. A long English now wraps into its own half
    instead of shrinking.
  * *A background per topic*: `justice` and `fairness` had none and `parents`
    had a prompt but no art. All ten topics now have their own motif, and there
    is a test that fails if any topic would fall back to the generic layer or if
    a topic has no art prompt written for it.
  * *Resume*: `RESUME.md` is the written contract and `tools/resume.sh` is the
    command. It restores `.git/config`, reports whether a commit was lost,
    measures both budgets, checks the token, verifies the toolchain, runs the
    suite, and prints the next steps out of STATE.md.
  * *Budgets*: `tools/cleanup.py` reports the workspace against its 128 MB
    snapshot limit and the repo against its own, prunes git-ignored scratch, and
    prunes older Release assets while refusing to touch a tag any document
    references. `cleanup.yml` runs it weekly and then re-verifies that every
    clip the manifest advertises still exists — the one thing housekeeping must
    never break.
  * 104 tests. `tests/test_design.py` pins all four layout corrections, so the
    next person to touch the renderer cannot quietly undo them.

* **Phase 4a ✅ (2026-10-11)** — The robotic pauses, and English.
  * The complaint was right and the reference repo had already measured it:
    creators pause 1.5 times a minute, line-by-line synthesis 19-23. Ours was
    worse than theirs — every breath group was its own utterance with a flat
    0.30 s glued after it, *and* Piper already splits sentences internally, so we
    were double-segmenting. Fixed by `say_flow()`: read the whole passage in one
    pass; top the join up to a target instead of appending to whatever tail the
    model left; and use the phoneme string to tell whether the engine broke a
    sentence or a clause (`.` vs `,`) so each gets its own amount of air.
  * Measured, N=5: silence in the clip 12.0% -> **7.2%** (male voice) and
    15.3% -> **3.5%** (female). The pause *count* is noisy run to run (7.9-25.8
    for one configuration), so it is reported with its spread and not claimed as
    a win. Two "tweaks" were measured, found worse and dropped: slowing Urdu made
    pauses worse and barely changed duration.
  * `--narrate english` renders the same card with an English voice. Both
    English voices run 227-245 wpm at the model's own pace against a creators'
    median of 184.5, so pace is now declared per voice: 179 and 183 wpm. Lessac
    sounds better and carries a Blizzard research licence — flagged `test_only`.
    LibriTTS-R (CC BY 4.0, 904 speakers) is the one that can ship.
  * `tools/voice_metrics.py` measures delivery the way the reference study does
    (pauses >=150 ms per minute, semitones, wpm) so the two are comparable — and
    its own correctness is pinned by tests against synthetic audio with a known
    answer, because a wrong ruler makes every measurement wrong.
  * 91 tests (was 60). The Urdu normaliser strips Latin script and the English
    one must not; there is a test that fails if the two are ever interchanged.

* **Phase 4 ✅ (2026-10-11)** — Voice, relevance, cadence. Three things, all of them
  answers to a question that was asked rather than work that was scheduled.
  * **The narration voice was unshippable.** `facebook/mms-tts-urd-script_arabic`
    is **CC-BY-NC-4.0** — non-commercial. Measured against the two Piper Urdu
    voices: Piper is **6.4x faster** (RTF 0.08 vs 0.51), **63 MB vs 145 MB**, and
    **MIT**. New `islamic/voice.py`, default `ur_PK-fasih` (male), `aegis` female.
    Verified end to end — `--ref quran:81:8 --topic justice` renders 11.23 s in
    ~15 s wall and passes both gates.
  * **The robotic sound is the text, not the model.** Urdu omits short vowels, so
    the engine is guessing at sounds it cannot see (Ali & Hussain, CLT10: "it
    would not be possible to create a text to speech system of Urdu using this
    under-specified input text"). The free half is now `islamic/urdu.py`: footnote
    markers stripped **before** digits expand (`۱؎` was being read aloud as "one"),
    digits spelled as words, translator's brackets turned into pauses rather than
    deleted, ASCII punctuation replaced with `،` `۔`, and a script whitelist so a
    stray Latin letter cannot be spelled out by an Urdu voice.
  * **The reviewed mismatch is now a machine check.** The rule is *every claim the
    headline makes must be matched in the verse's own text* — a shared noun is not
    a relation. `daughters` + 81:8 fails and keeps failing however the headline is
    reworded. `--audit` then cleaned the reference lists themselves: **34/34 refs
    across 10 topics** are carried by their own headline, and three topics lost a
    verse that never supported them. Enforced in the plan job *and* in the render
    job, so a single-clip dispatch cannot bypass it.
  * Two silent-failure bugs found on the way: publishers mix Arabic and Urdu
    codepoints for the same letter, and `آ` arrives both precomposed and as
    `ا`+maddah — unfixed, the check would have quietly failed to match the exact
    words it exists to find.
  * `RESEARCH.md` written: the TTS measurement, the channel/format findings, and
    the concrete route to 3-5 clips a day (34 validated refs are already the seed
    pool; the binding constraint is pairings that survive the gate, not compute).

* **Phase 3 ✅ (2026-10-11)** — Publication gates, and the tests that keep them honest.
  * `tools/check_video.py` now enforces two kinds of check. **File checks**: container,
    codec, pixel format, 1080×1920, duration floor/ceiling, agreement with the build
    record, integrated loudness. **Correctness checks**, read from the build record:
    a citation exists; the sacred text is present; a Qur'an clip names its reciter and
    the source of its timings; the collection is on `TRUSTED_COLLECTIONS`; a hadith
    carries a grade line; the timed word count matches the words on the clip.
  * `tools/publish.py` gates every clip before copying it. A clip that fails is held
    back with its reason, the run exits non-zero, and — the part that matters — the
    previously published version stands rather than being deleted or overwritten.
    Verified: a clip with its `reciter` stripped is blocked, and the live copy keeps
    its own record.
  * `tests/test_gates.py`: 27 tests, standard library only, ~10 s. Runs on a laptop,
    in this sandbox and on a runner. `render.yml` runs it before spending a runner
    on a render, so a broken gate stops the run instead of passing everything.

  Two defects were found by actually using the new gate, and both are worth keeping:

  1. **The gate was wrong, not the renderer.** Its first run reported that a clip
     showed 21 words against 20 timed ones. The Arabic is 21 *whitespace tokens*
     because the Uthmani edition separates waqf marks (`ۚ`) and, in other verses,
     the verse-number marker. Counting was fixed to "a token containing a letter",
     a Unicode property rather than a hand-written range, and the rule is pinned by
     tests. A gate that cries wolf gets switched off. The comparison is also now a
     real cross-source check: the word count comes from quran.com's `audio.segments`
     and the text from alquran.cloud, so agreement means two publishers count the
     same words.
  2. **Published clips had no provenance in the repository.** Build records lived only
     in the git-ignored `output/`, so on a fresh checkout — a cloud runner, a new
     laptop — every committed clip failed the gate as unverifiable. `publish.py` now
     writes `<slug>.build.json` next to each published clip: a published video carries
     its citation wherever it goes, and the repository's own checks work on a bare
     checkout. Found by running the suite against a checkout with no build folder.

* **Phase 2 🔨 (2026-10-11)** — Cloud render built and rehearsed; dispatch pending a token.
  * `.github/workflows/render.yml`: plan -> one runner per clip (max-parallel 5) ->
    per-clip gate -> single publish job that writes the site, verifies it, uploads
    the Release and commits `web/`. No secrets: the automatic `GITHUB_TOKEN` covers
    both the release and the commit.
  * `library.json` is the clip plan, and `tools/plan_render.py` refuses a plan that
    would mislabel a clip. It also emits `require_audio`, so the gate knows a
    Qur'an clip must carry its recitation while a hadith card may be silent.
  * `tools/check_video.py` is the seed of the QA layer: mechanically true-or-false
    checks only. Verified both ways — three real clips pass; deliberate silent,
    landscape and truncated fixtures each fail with a specific reason.
  * `tools/publish.py` was reworked so a clip is discovered by its own build
    record. That is what lets five parallel runners upload two files each and
    still produce a correct manifest with citations. It is also non-destructive by
    default: rendering a subset no longer prunes the rest of the library off the
    site — which it did on the first rehearsal, and that is why `--exact` exists.
  * `setup.sh` is now runner-safe: a `pipi()` wrapper falls back to
    `--break-system-packages` for a runner's PEP 668 Ubuntu, and torch installs
    from an exclusive `--index-url` so pip cannot pull the CUDA wheel by mistake.
* **Phase 1 ✅ (2026-10-11)** — The studio renders, and the promise is verified.
  * Root-caused the hang to `apad` + `-shortest` (A/B proof in the outcome above)
    and bounded it with `whole_dur` + `-t`; added a deadline and a render log so a
    failure reports itself instead of eating the session.
  * `produce.narrate()` -> child process (`islamic/narrate.py`); the model no longer
    squats on 484 MB while ffmpeg encodes.
  * Re-rendered all three references, one at a time; published to `web/video/` with
    posters and a manifest. Verified word-level sync against `audio.segments`,
    monotonic ink accumulation, and −14.3 LUFS.
  * Fixed the static-Arabic fitter (line cap -> stage height): isnad 64 px -> 87 px.
  * Warmed the pending-word colour into the palette.
* **Phase 0 ✅ (2026-10-11)** — Foundations.
  * Found and removed a **duplicate renderer**: this session had rebuilt
    `cards.py` / `reveal.py` / `video.py` / `make.py` / `timing.py` while the repo
    already carried the superior `studio.py` / `produce.py` / `timings.py`. Kept
    the studio (authentic islimi + girih art, measured-ink centring, crossfade, poster
    publishing) and deleted the parallel stack, so one renderer owns the frame.
  * Deleted naat-era leftovers: `tools/build_manifest.py`, `tools/musicgen_onnx.mjs`,
    `.github/workflows/naat.yml`, `web/audio/`, the duplicate `web/videos.html`, and
    ~50 MB of debug renders under `output/`.
  * Adopted the operating discipline from `zainkhan122/yt-tts · reels-studio`:
    one-phase-per-session, `setup.sh` re-entry, ≤1 heavy job, retrieval over reading,
    cloud rendering on free runners, QA gates before publish, receipts in git.
  * Repaired the real font defect: three `.ttf` files were **GitHub 404 HTML pages**,
    so Urdu had been rendering with whatever font the shaper fell back to.
    `tools/fetch_fonts.py` now verifies magic bytes; `setup.sh` runs it.
  * Recorded the two blocking defects for Phase 1 (render hang, TTS OOM).
