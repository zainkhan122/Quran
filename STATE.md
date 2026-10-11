# State — 2026-10-11 (Phases 0-4b done; PUSHED; cloud dispatch is the next thing)

Resume capsule. One screen. **A new session starts by reading `RESUME.md`** and
running `bash tools/resume.sh`; this file is what that script reports from.
If this file and the repo disagree, the repo wins — fix this file.

## Where things stand

* **Everything is pushed.** `origin/main` is level with the local branch. The
  remote is now the source of truth, which is the only storage that has never
  lost a commit.
* **Phases 0-4b are complete.** The studio renders; the gates in
  `tools/check_video.py` stop a bad *file* reaching the site; the gates in
  `tools/check_relevance.py` stop a bad *pairing* ever being planned; and the
  four layout corrections from review are pinned by `tests/test_design.py`.
* **Cloud dispatch is the outstanding step.** The workflow is built and
  rehearsed and has never been run. That is the next real piece of work.
* **The voice question is open and it is now a spend decision**, not a
  technical one — see *Diacritization* below and `RESEARCH.md`.

## What changed in Phase 4b (the review corrections)

| asked for | done how | pinned by |
|---|---|---|
| Arabic ayah bold | outline stroke, not a font swap (Amiri has no bold) | `test_the_stroke_changes_the_ink` |
| light-dark transparency behind text | body scrim 88 → 132 of 255 | `_body_scrim` |
| Urdu/English headings same size | independent fit, then both re-set to the smaller | `test_english_and_urdu_headings_render_at_one_size` |
| translation: Urdu top, English bottom, equal halves | body zoned into two halves, each centred | `test_halves_do_not_overlap` |
| a different background per video | all 10 topics have their own motif | `test_no_topic_falls_back_to_the_generic_layer` |

## Run these before you commit

```bash
bash tools/resume.sh                           # restore + verify + report, ~1 min
python3 -m unittest discover -s tests          # 104 tests, ~12 s, stdlib, offline
python3 tools/check_relevance.py --audit       # topic vs its own refs (network)
python3 tools/plan_render.py --plan --offline  # the plan the workflow would build
python3 tools/cleanup.py                       # both budgets, changes nothing
python3 tools/publish.py                       # gate every clip, then write the site
```

## The one thing blocking cloud dispatch: nothing

The token works and is at `/tmp/.ght` (0600, deliberately outside `/home/user`
so it is never snapshotted). Push is done. The next step is simply to dispatch:

```bash
printf '%s' '<token>' > /tmp/.ght && chmod 600 /tmp/.ght     # if /tmp was wiped
tools/cloud.sh render quran-81-8                            # ONE clip first
tools/cloud.sh runs ; tools/cloud.sh logs <id>
```

Compare the runner's output against the local render of the same clip —
duration, size and loudness should agree. If it holds, dispatch the library.

## Diacritization — investigated, and it is a dead end for free

Urdu omits short vowels, so the engine guesses. Harakat demonstrably change the
phonemes (6 of 8 test words), so the root cause is reachable *in principle*.
Every free route was tried and rejected on evidence:

* hand-written harakat — the two words a native ear could check both got worse;
* Piper's bundled tashkeel model — it is Arabic, and it turns `دعا` into
  "daa-anaa";
* Hugging Face has no Urdu diacritization model of any kind.

The remaining gap is the **acoustic model**. That means a heavier engine on
Actions (Chatterbox-class, MIT, which the reference repo uses and which cannot
run in this sandbox), i.e. a decision about spending free CI minutes.

## The published set

Three clips in `web/video/`, each with its `.build.json` provenance record.
Quality: 1080×1920@30 h264 high + AAC 192k 44.1 kHz, `+faststart`.

| reference | seconds | size | note |
|---|---|---|---|
| `quran:81:8` | 11.23 | 1.2 MB | pre-dates the 4b layout fixes |
| `quran:30:21` | 52.58 | 6.0 MB | pre-dates them too |
| `ibnmajah:224` | 47.60 | 4.3 MB | pre-dates them too |

**All three need re-rendering** to pick up the bold ayah, the stronger scrim,
the equal headings and the equal translation halves. That is one dispatch.

## Verified, with the measurement, so it does not have to be re-checked

* **Word-level sync is real.** Settled-word ink grows at t≈1.0 / 1.5 / 2.9 s for
  `quran:81:8`, matching `audio.segments`. Timings come from the publisher's own
  response — do not reintroduce a forced aligner.
* **Flow reading works.** Silence in the narration track fell 12.0% → 7.2%
  (male voice) and 15.3% → 3.5% (female), N=5. The pause *count* is noisy run to
  run (7.9–25.8 for one configuration) and must not be quoted precisely.
* **The relevance audit is clean.** 34/34 refs across 10 topics are carried by
  their own headline. `daughters` + `quran:81:8` is refused, and stays refused.
* **All 10 topics have their own background art**, with a written prompt for
  each in `tools/motifs.py`.
* **The workspace is inside budget**: 101.7 MB against the 128 MB snapshot
  limit, reported by `python3 tools/cleanup.py`.

## Environment (not persisted — restored by `tools/resume.sh`)

```bash
bash setup.sh --check     # ~9 s: ffmpeg, wheels, raqm shaping, fonts, ornament
bash setup.sh             # ~3 min cold: the repair/install path (+ voice weights)
bash setup.sh --with-mms  # only if you need the old CC-BY-NC voice for an A/B
```

Three things never survive a snapshot, each for a reason:

* `.git/config` — a credential path, excluded on purpose;
* `~/.cache` — the Urdu voice weights (~60 MB), refetched by `setup.sh`;
* `/tmp/.ght` — the token, deliberately outside the workspace.

`.git` itself has also been rolled back twice while the working tree survived.
`naat-ai-ahead.bundle` beside the repo restores local commits in one command.

## Next session, in order

1. `bash tools/resume.sh` — it does the whole of the orientation for you.
2. **Re-render the three clips.** The layout changed, so the published set is
   stale. Locally that is one command per clip; in the cloud it is one dispatch.
3. **Dispatch one clip** (`tools/cloud.sh render quran-81-8`) and compare the
   runner's output against the local render — duration, size and loudness.
4. If it holds, dispatch the full library and confirm the Release and the site
   commit. Then mark Phase 2 done.
5. Phase 5: grow `library.json` from the 34 validated refs (~10 at a time,
   `--audit` after each batch) and add `--daily N` rotation for the 3-5/day
   cadence.
6. **Get a native Urdu speaker to hear `docs/samples/voice-samples.mp3`.** Every
   number in this project is a proxy; that is the only test that settles it.

## Open items, honestly

* **No Urdu speaker has heard the output.** WER against whisper-base is a weak
  proxy and could not distinguish the voices.
* **The relevance gate cannot certify a translation.** It checks that the words
  the headline claims occur in the text we display. It cannot read context and
  it cannot see a metaphor. It is a tripwire, not a review.
* **The published clips still carry the old layout and two carry the
  non-commercial MMS voice.** Re-render before any monetisation.
* **The workspaces of the past are gone.** Two commits were lost to snapshot
  resets before the push habit and the bundle existed; assume nothing local is
  safe and push at every phase boundary.
* **A weekly cron is not a verified cron.** `cleanup.yml` is scheduled, but
  GitHub disables scheduled workflows after 60 days of repo inactivity and the
  schedule has not been observed to fire. Run it by hand if months have passed.
