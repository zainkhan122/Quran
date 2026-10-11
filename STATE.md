# State — 2026-10-11 (Phases 0-4c done; PUSHED; cloud dispatch is the next thing)

Resume capsule. One screen. **A new session starts by reading `RESUME.md`** and
running `bash tools/resume.sh`; this file is what that script reports from.
If this file and the repo disagree, the repo wins — fix this file.

## Cloud: LIVE and verified (2026-10-11)

**Site: https://zainkhan122.github.io/Quran/**. Local and GitHub are in sync;
nothing is waiting on a token.

| piece | state | proof |
|---|---|---|
| `render.yml` | **green**: plan, 3 parallel renders, publish, Pages | run 38134186361, ~3.5 min end to end, 59-97 s per clip |
| `pages.yml` | green, deploys from an artifact | 13-16 s; the live manifest timestamp equals the repo's |
| `cleanup.yml` | green (dry run); weekly cron Sun 04:00 UTC | marked both releases LIVE, refused to prune them, 6/6 assets present |
| Releases | `renders-2026-10-11` (clips, posters, records), `voice-approval` (audition pack) | `tools/fetch_media.py --check` |
| git | **0 media files**; `.git` 18 MB | `test_no_media_is_tracked_by_git` |
| fidelity | cloud durations = local to 0.01 s; voice `en_michael` | build records |

The first three cloud runs failed, and each failure was a real defect that had
never run before: the plan job had no Pillow; a test assumed media in the
checkout; the publish job had no ffmpeg (it held every clip back, which is the
fail-safe working). All three are fixed.

**Operating it** (token in `/tmp/.ght`; it does not survive a session):

    tools/cloud.sh render               # whole library, waits for the run
    tools/cloud.sh render quran-30-21   # one clip
    tools/cloud.sh runs | logs <id> | wait <id>

To add or retire a clip, edit `library.json` and render. A clip is retired by
leaving the plan, never by deleting files.

**Observed, not explained:** a PAT push touching `web/` did not start
`pages.yml`, although the workflow is active and the push event was recorded.
Nothing depends on it, because `render.yml` calls Pages directly and dispatch
works. If the site ever looks stale, run `python3 tools/ghapi.py dispatch pages.yml`.

**Security:** the token reached the workspace once as an uploaded file
(`uploads/Github.txt`). It was moved to `/tmp/.ght` and the file shredded at
once, but a snapshot may already have caught it. **Rotate the token.**

## Cadence: the recommendation (2026-10-11)

The owner asked for 3-5 shorts a day. The recommendation is to **start at 3 a
day and earn the move to 5.** The limit is not render capacity: a free runner
renders a clip in minutes. The limit is the pool of verified material.

* **3 slots a day, tied to the day's rhythm** (Pakistan time): after Fajr
  (~06:30), after Zuhr (~13:30) and after Isha (~21:00). One slot each for
  Qur'an, Hadith and Du'a, each on a different topic.
* **No topic twice within 48 h; no reference again within 90 days.** At 3 a day
  that needs about **270 verified refs** for a clean 90-day cycle. Today there
  are **32**, so the pool, not the schedule, is the bottleneck. Phase 5 grows it
  ~10 refs at a time, each batch through `islamic.verify` and `--audit`.
* **Go to 4-5 a day only when** the pool has more than 90 days of material at
  that rate, and the first weeks show retention holding. Volume that repeats
  itself, or that outruns review, costs more than it earns.
* **Consistency beats volume.** The same slots every day matter more than the
  count.
* Uploading to YouTube is **not automated yet.** API uploads now have their own
  bucket of 100 calls a day, separate from the 10,000-unit pool, so the quota is
  not the constraint. YouTube does restrict uploads from an unaudited API
  project to *private* until the project passes its compliance audit. Until
  then, upload by hand from the published set, or get the API project audited
  first.

## Voice: APPROVED — Michael (Kokoro am_michael)

The English narration was rejected — *"TTS is very bad for English. use male
sound."* — and both halves of that turned out to be measured, one of them our
mistake.

**The engine was Piper** (`rhasspy/piper`, a 2023 VITS model). The voice we
shipped as the English default, `en_US-libritts_r-medium` speaker 60, was
catalogued **male** and **measures 248-250 Hz — the female range.** The owner
heard a defect we had recorded as a fact, and the catalogue was wrong.

**The owner auditioned six male voices and chose "Michael."**
the `voice-approval` release (`voice-audition-en.mp3`) is the pack that was approved and
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
voice" item. The old Urdu sample reel (`voice-samples.mp3`) was deleted in the
2026-10-11 media cleanup; `--narrate urdu` regenerates one if it is ever needed.

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
