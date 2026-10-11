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
| 1 | **Make the studio render at all.** Fix the ffmpeg tail-hang; move Urdu TTS into a short-lived process; render the three clips | 3 MP4s + posters + `manifest.json` | ⏳ next |
| 2 | **Cloud render.** Free GitHub runners (4 vCPU / 16 GB) instead of the 2 GB sandbox; outputs to a Release; secrets in Actions | `.github/workflows/render.yml` | |
| 3 | **QA gates.** Machine checks that must pass before a video reaches `web/video/` | `tools/qa.py` + gate wired into publish | |
| 4 | **Coverage.** `parents` motif (8th of 8), verify the seeded topic references against a human-checked list, render the 8-topic library | clips for every topic | |
| 4b | optional: regenerate `assets/motifs/` procedurally from the prompts in `tools/motifs.py`. The earlier geometric generator was retired in Phase 0 as unused duplication — the committed PNG set is the source of truth, so regeneration needs a spec first | | |
| 5 | **Publishing.** Site polish; optional scheduled render + release; a receipt journal so nothing is ever re-uploaded | | |
| 6 | optional: long-form cuts, landscape variants, an analytics loop (views → topic picks) | | |

### Known work for Phase 1 (carry-over detail, so the next session does not re-derive it)

* **ffmpeg tail-hang.** `islamic/studio.py:render()` feeds frames over stdin and
  the encode never finishes. Reproduced twice: the writer gets all frames through
  (375 frames fed in 4.9 s) and then waits forever at the close. Standalone encodes
  of the same size/preset take seconds, so it is the command shape, not x264 —
  prime suspects are `apad` on the audio plus `-shortest` in a filter-complex feed,
  and AAC's encoder delay. Fix: give the audio an exact `-t` and drop `apad`/
  `-shortest`, or write the timeline to WAV first. **Always bound any render with a
  timeout** so a hang costs a minute, not the session.
* **Urdu TTS OOM.** `islamic/produce.py:narrate()` runs the model in the render
  process; `del` + `gc.collect()` leaves ~484 MB of torch arenas resident, and
  ffmpeg then dies by signal (empty stderr). `islamic/narrate.py` already does the
  job in a child process that exits before encoding starts — wire `produce.py` to
  call it. Measured: 484 MB is the floor after freeing; the child approach returns
  the whole box.
* **Pending-word colour.** In `studio.py` the not-yet-recited words draw in a cold
  steel tone. Warm it toward the palette (dim gold/ivory) before the first render.

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
