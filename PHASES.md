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
4. **End the session with:** workspace clean, `PHASES.md` status + phase log
   updated, `STATE.md` refreshed, everything committed and pushed.
5. **Never leave a half-edited file.** Re-run the file after each patch; a
   partial edit once left a `NameError` in the manifest builder that only surfaced
   in the next session.

## Phases

| # | Session goal | Deliverable | Status |
|---|---|---|---|
| 0 | **Foundations.** One renderer (two existed), clean tree, phased plan, state capsule, repo pushed | this file, `STATE.md`, single-source renderer, clean tree | ✅ 2026-10-11 |
| 1 | **Make the studio render at all.** Fix the ffmpeg tail-hang; move Urdu TTS into a short-lived process; render the three clips | 3 MP4s + posters + `manifest.json` | ✅ 2026-10-11 |
| 2 | **Cloud render.** Free GitHub runners (4 vCPU / 16 GB) instead of the 2 GB sandbox; outputs to a Release; secrets in Actions | `.github/workflows/render.yml` | ⏳ next |
| 3 | **QA gates.** Machine checks that must pass before a video reaches `web/video/` | `tools/qa.py` + gate wired into publish | |
| 4 | **Coverage.** `parents` motif (8th of 8), verify the seeded topic references against a human-checked list, render the 8-topic library | clips for every topic | |
| 4b | optional: regenerate `assets/motifs/` procedurally from the prompts in `tools/motifs.py`. The earlier geometric generator was retired in Phase 0 as unused duplication — the committed PNG set is the source of truth, so regeneration needs a spec first | | |
| 5 | **Publishing.** Site polish; optional scheduled render + release; a receipt journal so nothing is ever re-uploaded | | |
| 6 | optional: long-form cuts, landscape variants, an analytics loop (views → topic picks) | | |

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
