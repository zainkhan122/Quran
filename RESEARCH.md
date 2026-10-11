# RESEARCH

What we learned from outside the repo, and what we decided because of it.
Everything here is either a measurement taken on this box or a claim with its
source named. Where a source was read but its URL was not pinned, that is said
plainly rather than papered over with a citation that looks better than it is.

Three questions are answered: **why the Urdu narration sounds robotic**, **what
the short-form Islamic channels actually do**, and **how 3-5 videos a day is
supposed to work**.

---

## 1. Why the Urdu narration sounds robotic

### The cause is the text, not the model

Urdu orthography writes the consonants and **omits the short vowels**. Handed
`علم`, a synthesiser cannot know whether it is *ilm*, *alam* or *ulam*.

> "it would not be possible to create a text to speech system of Urdu using this
> under-specified input text"
> — Ali & Hussain, *Automatic Diacritization for Urdu* (CLT10)

That is the whole problem. Diacritic absence is named first among the causes
along with complex phonetics and dialectal variety (MDPI, *Towards a More
Natural Urdu*). Hybrid diacritization systems reach ~95.2-95.4% accuracy, and
pre-2025 Urdu naturalness scores sat at **MOS 2.90-3.45** — barely above
"robotic" on a 1-5 scale. No amount of model-swapping fixes an input that does
not say what it means.

### What we can actually do about it, in order of effect

**1. Stop handing the engine things it was never designed to say.** This is
free, determinate, and it is now `islamic/urdu.py`. Real defects that were
reaching the voice from our own published copy:

| defect | example | what happens without the fix |
|---|---|---|
| footnote marker | `... کی طرح ہے ۱؎۔` | `۱؎` is read as the spoken word for "one" |
| translator's bracket | `نشانات (اور تصرفات) میں` | brackets cost the pause, so the aside runs into the sentence |
| bare digits | `500` | digits have no fixed Urdu reading; MMS fails on them outright |
| ASCII punctuation | `,` `.` | the engine derives pauses from `،` `۔`; ASCII gives it nothing |

Each of those is a test in `tests/test_relevance.py`. The rule for markers is
subtle and was got wrong at first: **footnote markers must be stripped before
digits are expanded**, or `۱؎` becomes a spoken "one" tacked onto the end of a
hadith.

**2. Use a voice we are allowed to ship, that runs at 0.08 RTF.** Measured on
this box, three real sentences of our own copy:

| voice | licence | size | load | RTF | WER\* |
|---|---|---|---|---|---|
| `facebook/mms-tts-urd-script_arabic` (was shipping) | **CC-BY-NC-4.0** | 145 MB | 3.8 s | 0.51 | 26.6% |
| `ur_PK-fasih` — Piper, male | MIT | 63 MB | 2.1 s | **0.08** | 26.6% |
| `ur_PK-aegis_female` — Piper, female | MIT | 63 MB | 1.8 s | **0.08** | 22.8% |

\* transcribed back with `openai/whisper-base`. **Read that column with
suspicion.** All three land within four points of each other, which means the
ASR is the floor, not the voices — it cannot discriminate between them. It is
recorded because it is a result we obtained, not because it decides anything.
An earlier single-sentence run showed the female voice at 3.7% against the male
voice's 25.9%; that was one sentence, and the three-sentence run dissolved it.
**Do not build on the single-sentence number.**

Two things in that table *do* decide:

* **The licence.** `CC-BY-NC` is non-commercial. A channel that is monetised, or
  might be, cannot ship narration under it. That is not a quality trade-off, it
  is a hard stop. Both Piper Urdu voices are MIT. Note the trap: a third-party
  site claimed Piper Fasih was "personal and non-commercial only" while the
  Hugging Face MODEL_CARD for the same voice says `license: mit`. **Always check
  the MODEL_CARD at the source**, never a directory listing.
* **The speed.** RTF 0.08 against 0.51 is 6.4x, and 63 MB of ONNX against
  500 MB of torch allocator arenas is the difference between a render that fits
  a 2 GB sandbox and one that gets ffmpeg OOM-killed.

So the default engine is now **Piper `ur_PK-fasih`** (male — the norm for Urdu
religious narration), `ur_PK-aegis_female` one flag away. Verified end to end:
`python3 -m islamic.produce --ref quran:81:8 --topic justice` renders 11.23 s at
1080x1920 in ~15 s wall, and passes both the video gate and the topic gate.

**3. Write for the voice.** `،` and `۔` instead of ASCII; one idea per sentence;
numbers as words (`پانچ سو`, not `500`); native script and never Roman. All
enforced in `islamic/urdu.py`, so it happens whether or not anyone remembers.

### The pauses were ours, not the engine's

A second listening pass produced the right complaint: *"it is more robotic…
the reference repo uses fluent script so that TTS is not pausing at each
sentence and gives robotic pauses."* That was correct, and the reference repo
had already measured it: creators pause **1.5 times a minute**, line-by-line
synthesis **19–23**, fixed there by reading consecutive lines in one pass.

Our pipeline had the same defect in a worse form. Every breath group was
synthesised as its own utterance and a flat **0.30 s** was appended after each.
Worse still, Piper's `synthesize()` *already* splits on real sentence
punctuation internally and returns one chunk per sentence - so we were
double-segmenting: cutting sentences apart ourselves and then gluing silence
into the gaps we had just made.

The fix is `say_flow()` in `islamic/voice.py`: hand the engine the whole passage
and let it decide where its sentences are. Two details that matter more than
they look:

* **The join is topped up, not appended.** The model already ends each chunk
  with its own tail of quiet. Appending a flat 0.30 s makes the real pause
  "0.30 s + whatever the model left", which varies per chunk. `_tail_silence()`
  measures that tail and adds only the difference.
* **The engine says which kind of break it made.** A chunk carries no text, but
  it carries its phonemes, and eSpeak keeps the punctuation in them: a chunk
  that ended on `۔` comes back ending in `.`, a clause comes back ending in `,`.
  So a sentence gets 0.30 s and a clause 0.14 s without us re-parsing anything.

Measured, N=5 runs, same text, same voice, old method against new:

| voice | condition | silence in clip | pauses/min |
|---|---|---|---|
| `fasih` (male) | line-by-line + 0.30 s glue | 12.0% | 20.9 ± 5.6 |
| `fasih` | **flow** | **7.2%** | 16.3 ± 4.6 |
| `aegis` (female) | line-by-line + 0.30 s glue | 15.3% | 16.5 ± 2.7 |
| `aegis` | **flow** | **3.5%** | 8.1 ± 4.4 |

**Read the right-hand column with suspicion.** Single runs of the *same*
configuration ranged from 7.9 to 25.8 pauses/min - Piper samples internally, so
each run's pauses land in slightly different places, and the spread is wider
than the effect. The pause *count* is not a number we can honestly claim to have
cut. The **silence fraction is the stable signal**: dead air roughly halves, and
that is the thing you actually hear.

A negative result, kept because it was measured: slowing the Urdu voice
(`length_scale` 1.06) made the pauses *worse* (21.4/min, 8.5% silence) and barely
changed the duration at all (16.72 s → 16.99 s). Tighter joins (0.24/0.11) were
also worse on one run each. Both were abandoned rather than kept as "tweaks".
Urdu stays at the model's own pace.

### English, and whether it is any better

Asked for directly: *"make a video with English script/TTS to check its
quality."* `--narrate english` now renders the same card with the English voice
speaking the English translation instead of the Urdu one; the frame still shows
both languages either way.

| voice | licence | speakers | pace, model default | pace shipped |
|---|---|---|---|---|
| `en` - Lessac | Blizzard 2013 research licence | 1 | 227 wpm | 179 wpm at `length_scale` 1.4 |
| `en_free` - LibriTTS-R | **CC BY 4.0** | 904 | 245 wpm | 183 wpm at `length_scale` 1.6 |

Creators run at a median of **184.5 wpm**, which is where the shipped numbers
come from. Both voices are *too fast out of the box* by a wide margin - that is
not a subtlety, it is 40 wpm.

The honest split: **Lessac is the better voice** by common report and it is the
one heard in the sample pack, but its MODEL_CARD points at a Blizzard research
licence, so `test_only` is set on it and it must not go into a published clip.
**LibriTTS-R is the one that can ship** (CC BY 4.0, 904 speakers - a different
speaker id is a different voice, so there is room to pick a favourite).

One more trap worth recording: the Urdu normaliser **strips Latin script** (an
Urdu voice cannot say it, so `islamic/urdu.py` deletes it). Pointed at an
English script it would silently reduce the narration to rubble. `narrate()`
therefore picks its normaliser from the voice's language, and there is a test
that fails if the two are ever interchanged.

### What is still out of reach

Real diacritization. Restoring the harakat needs a model, and the CPU-only,
2 GB budget does not have room for one. Tacotron-class Urdu is the quality
ceiling in the literature (WER 13.1% against MMS's 25.6%, per the Interspeech
2025 benchmark) but it needs a GPU — cloud-only if it is ever worth it. The
honest summary: **we removed the defects we were injecting ourselves, and
switched to a voice we are allowed to use; we did not make an under-specified
script specify itself.**

Non-solutions, recorded so nobody retries them: Meta MMS (fails on digits and
symbols, and CC-BY-NC), Kokoro (ranked best by ear in a hi_IN comparison, but
0.7-0.9 GB and ~0.5x real time on 2 threads — too heavy here).

---

## 2. What the short-form Islamic channels actually do

Read from channel listings, format guides and platform documentation. **No
channel's media was downloaded, copied, or reused** — the analysis is of public
format and structure only, and their clips are never an asset source.

### The format

| element | finding |
|---|---|
| hook | 0-3 s, **spoken and on-screen** — it has to read on mute |
| structure | 3-10 s name the tension, 10-22 s payoff, 22-30 s one CTA |
| length | 15-45 s TikTok/IG; 30-60 s YouTube Shorts |
| cadence | every 1-3 days; remake top performers rather than always minting new |
| title/SEO | keyword in the first ~40 characters; keyword visible in the first frame; ≤8 tags, 3 primary |

"The first three seconds are a promise." Our current set is 11.6 s, 52.6 s and
47.6 s — the two long ones are inside the YouTube window and outside TikTok's.
Long ayahs are the constraint: 30:21 runs 52 s because the *recitation* runs
that long, and cutting a recitation is not available to us.

### Channels looked at

Visual Quran (surah-by-surah, Urdu voiceover *tarjuma* — the closest existing
model to what we build), Islam with Aisha (~650K, Urdu tafseer), IQRA Cartoon,
Paigham TV, One Islam Shorts, FawwazFayyadh. **Avoid `iimatheen` as a model** —
community discussion flags it as hadith-rejector-adjacent, which is
disqualifying regardless of production quality.

The competitor pattern worth matching is Tashghil.Pro's maker: 200+ reciters,
Uthmani script, auto-captions. That is the floor, not the ceiling.

### The constraint that decided a design question

`islamqa.info` answer **175174** sets out the ruling on pairing Quran with
video: the scene must **match the verse's meaning**; no music; no women shown;
never pair worldly imagery with verses about the Unseen (Paradise, Hell).
Matched scenes are fine — the camel with 88:17 is the example given.

We already hold to the no-music and no-animate-beings rules. The scene-matching
rule is the one that was being broken in a way we had not mechanised: see §3.

### The authenticity floor we inherit

A KW-publications paper on hadith misuse states the standard we already meet and
should keep meeting: **reference required, Arabic original included, no personal
tafsir bolted on to the dalil.** Our gate enforces the first two mechanically
(`reference`, `source`, non-empty Arabic, `grade` for hadith); the third is a
writing rule, not a checkable one.

---

## 3. Topic must be carried by the verse — now a gate, not a note

The review was one line: *"its topic and actual ayah has NO relation. Such
topic/ayah to be avoided."* About a clip headed **"Daughters — a blessing to be
cherished"** over **81:8, "and when the girl who was buried alive is asked"**.

It is worth being precise about why that was wrong, because the naive objection
is the exact reasoning error: *81:8 is about a girl, the topic is about
daughters, so they match.* 81:8 is about a **crime**. The headline asserted a
**blessing**. The subject matched; the claim did not. **A shared noun is not a
relation.**

So the check is not "do the topic and the ayah share a keyword". Each topic now
declares the claims its headline makes, and the words that would substantiate
them; a pairing passes only if **every claim the headline makes is matched in
the verse's own Urdu translation**. `daughters` requires `daughters` *and*
`worth`; 81:8 supplies the first and never the second, and keeps failing however
the headline is reworded. That is the point.

Implemented in `islamic/relevance.py`, run by `tools/check_relevance.py`, and
enforced in **two** places: `tools/plan_render.py` (so the `plan` job refuses
before a runner is spent) and the render job's **Gate the topic** step (so a
single-clip dispatch cannot bypass the plan).

Running it over every topic's whole ref list — `--audit` — cleaned up the
reference lists themselves. It found:

* `daughters` was listing 81:8-9, 16:97 and 17:31. None of them says what the
  headline said. 81:8 moved to a new **`justice`** topic, re-housed rather than
  relabelled; 42:49-50 ("He grants daughters to whom He wills") and Tirmidhi
  1913 ("they will be a barrier from the Fire") actually carry it.
* `children` listed 17:24, whose words are about kindness *to* parents — it
  belongs to `parents` only.
* `business` listed 62:10, which is about seeking provision after prayer, not
  honesty in a dealing.
* `women` listed 4:1, about creation and kinship, which does not carry "equal
  reward".
* `justice` had swallowed 4:135 and 16:90; they *command* justice without naming
  anyone wronged, so they became their own topic, **`fairness`**.

**Audit result: 34 of 34 refs across 10 topics are now carried by their own
headline.** Two bugs surfaced along the way, both of which would have silently
passed bad content: publishers mix Arabic and Urdu codepoints for the same
letter, and `آ` arrives both precomposed and as `ا`+maddah — folding is now
explicit and tested.

### The limit of this check, stated once

It is a **lexical check on a translation**. It cannot certify that a translation
is theologically right, it cannot read context, and it cannot see a metaphor —
which is why the `knowledge` headline had to be made literal ("read, and ask for
more", which 96:1 and 20:114 say) rather than "a path that never ends", which
none of them do. It is a tripwire for one specific, expensive failure mode. It
is not a substitute for review.

---

## 4. How 3-5 videos a day is supposed to work

The current library has **3 clips**. Five a day needs a library an order of
magnitude bigger, and the good news is that the audit already found the seed
material: **34 validated refs across 10 topics** (marriage, children, daughters,
business, women, parents, knowledge, prayer, justice, fairness). Several are
ranges (2:282, 33:35) that split into more than one clip.

The plan, in order:

1. **Grow `library.json` from the validated pool**, in batches of ~10, running
   `--audit` after each batch so a bad pairing is caught at the point of entry
   rather than at the point of publishing. Target 35-40 clips.
2. **Add `--daily N` rotation to `tools/plan_render.py`**: select N clips by
   `(day_of_year * N) % total` so each day renders a different set and the cycle
   length is `total / N` days. This needs no state, which matters — a scheduled
   job with no memory is a scheduled job that cannot drift.
3. **Only then** wire `schedule:` into the workflow.

Two things to be honest about at step 3: a cron cannot be verified from here,
because dispatching needs a token that is currently missing (see `STATE.md`);
and **GitHub disables scheduled workflows on a repository after 60 days of
inactivity**, so a cron is a fragile primary path. The `workflow_dispatch` call
is the reliable one.

Budget check against the numbers we measured: a clip is ~15 s of wall time and
~1.2-6 MB. Five a day is well inside a free runner's capacity, and the binding
constraint is not compute — it is having five verse/topic pairings a day that
survive the relevance gate.

---

## 5. What this document does NOT cover

Stated so it is not mistaken for done:

* **No actual video was downloaded or analysed frame by frame.** The channel
  research is from listings, format guides and published rulings — not from
  inspecting clips. Nothing in §2 rests on having watched or measured a specific
  video, and no channel's media was used.
* **URLs are not pinned for most sources.** They are named (publication, article
  title, or answer number) so they can be found again; the citations are only as
  strong as that.
* **The voice switch is verified for one clip, in two languages.** `quran:30:21`
  and `ibnmajah:224` have not been re-rendered on Piper. The 52 s clip is the one
  to watch — it is the longest narration and the likeliest place for a
  breath-group problem to show up.
* **No Urdu speaker has listened to the output.** WER against whisper-base is a
  proxy, and a weak one: it could not tell the voices apart. The only test that
  settles "does it still sound robotic" is a native speaker hearing it. The
  sample pack (`urdu-english-voice-samples.mp3`) exists to make that judgement
  possible rather than to substitute for it.
* **The delivery metrics are not the reference study's metrics.** Ours are
  computed here, with autocorrelation pitch tracking instead of Praat, on audio
  with no music bed. The numbers are comparable in shape - pauses per minute,
  semitones, wpm - but they were not produced by the same tool, so treat them as
  the same *kind* of measurement, not the same measurement.
