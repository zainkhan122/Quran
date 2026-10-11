"""
Video assembler: cards + audio -> vertical MP4.

Audio policy (this is the part that matters for correctness):

  Quran  -> REAL recitation, per-ayah MP3 from everyayah.com (Alafasy 128 kbps).
            Never TTS. Arabic Quranic text has tajweed rules that no free TTS
            model implements, and mispronouncing Quran is not a cosmetic issue.
  Urdu   -> our Urdu TTS (naat.tts), narrating the published Urdu translation.
  Arabic hadith -> displayed, not synthesised, unless --arabic-tts is passed.

Card order: Arabic (+recitation) -> Urdu translation (+narration) -> optional
English. The Arabic is always on screen while its own audio plays, so the viewer
can follow the text.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .cards import Theme, write_card
from .sources import VerbatimItem, has_isnad

SR = 44_100
EVERYAYAH = "https://everyayah.com/data/Alafasy_128kbps"


@dataclass
class VideoSpec:
    width: int = 1080
    height: int = 1920
    fps: int = 24
    hold_pad: float = 1.2       # seconds of card before/after its audio
    zoom: float = 0.06          # Ken Burns strength
    draw_border: bool = True


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd[:12])}...\n{p.stderr[-1500:]}")


def _dur(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def fetch_recitation(item: VerbatimItem, out_dir: Path, reciter_dir: str = "Alafasy_128kbps") -> Path | None:
    """Download the real recitation for a Quran ayah. Returns concatenated audio."""
    if item.kind != "quran":
        return None
    # reference is "quran:30:21" — take everything after the "quran:" prefix,
    # not just the first colon-separated field.
    ayah = item.reference.split(":", 1)[1]           # "30:21"
    s, a = ayah.split(":")
    url = f"https://everyayah.com/data/{reciter_dir}/{int(s):03d}{int(a):03d}.mp3"
    raw = out_dir / f"rec_{s}_{a}.mp3"
    if not raw.exists():
        import urllib.request
        try:
            urllib.request.urlretrieve(url, raw)
        except Exception as e:
            print(f"[video] recitation unavailable ({e}); falling back to TTS")
            return None
    # normalise to our working format
    wav = out_dir / f"rec_{s}_{a}.wav"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
          "-ar", str(SR), "-ac", "1", str(wav)])
    return wav


def narrate_urdu(text: str, out_path: Path, engine: str = "mms") -> Path:
    """Urdu narration of the translation using our existing TTS stack."""
    import gc
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from naat.tts import NaatTTS, split_breath_groups

    tts = NaatTTS(engine=engine)
    tts.load()
    src_sr = tts.sr
    groups = split_breath_groups(text)
    if not groups:
        raise RuntimeError("nothing to narrate")
    parts: list[np.ndarray] = []
    for i, g in enumerate(groups):
        try:
            parts.append(tts.say(g, seed=100 + i))
            parts.append(np.zeros(int(tts.sr * 0.30), dtype=np.float32))
        except Exception as e:
            print(f"[video] narration skip: {e}")

    # Release the TTS model BEFORE ffmpeg starts. Holding ~750 MB while x264
    # encodes a 1080x1920 frame exhausted the 2 GB sandbox and got ffmpeg
    # SIGKILLed with empty stderr.
    tts._model = None
    tts._tok = None
    del tts
    gc.collect()
    try:
        import torch
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    except Exception:
        pass

    full = np.concatenate(parts)
    peak = float(np.abs(full).max()) or 1.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".raw.wav")
    sf.write(tmp, (full / peak * 0.92).astype(np.float32), src_sr)
    # resample to 44.1 kHz stereo to match the recitation segments exactly
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp), "-ar", str(SR),
          "-ac", "1", str(out_path)])
    tmp.unlink(missing_ok=True)
    return out_path


def _segment(card: Path, audio: Path | None, out: Path, spec: VideoSpec,
             dur: float) -> float:
    """One card + its audio, with a slow zoom. Returns final duration."""
    frames = max(int(dur * spec.fps), 1)
    z = spec.zoom
    # zoompan works on the upscaled image; pre-scale to avoid jitter artifacts
    pre = f"scale={spec.width*2}:{spec.height*2}"
    zp = (f"zoompan=z='min(zoom+{z/(frames*1.0):.6f},{1+z})'"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={spec.width}x{spec.height}:fps={spec.fps}")
    vf = f"{pre},{zp},format=yuv420p"
    if spec.draw_border:
        vf += (f",drawbox=x=0:y=0:w=iw:h=ih:color=0xD9B169@0.35:t=4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(card)]
    if audio is not None:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", vf, "-t", f"{dur:.3f}", "-r", str(spec.fps),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p"]
    if audio is not None:
        # Sample rate and channel count MUST match across every segment: the
        # concat demuxer with -c copy silently drops streams that differ, which
        # left a 49 s video carrying only 28 s of audio.
        cmd += ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]
    _run(cmd)
    return _dur(out)


def build_video(
    item: VerbatimItem,
    out_path: str | Path,
    work_dir: str | Path = "output/video",
    spec: VideoSpec | None = None,
    theme: Theme | None = None,
    engine: str = "mms",
    include_english: bool = False,
    add_backing: bool = True,
) -> dict:
    spec = spec or VideoSpec()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    th = theme or Theme()
    info: dict = {"reference": item.reference, "source": item.source, "segments": []}

    phases: list[tuple[str, str, Path | None]] = []   # (card_kind, text, audio)

    # --- phase 1: Arabic + real recitation ---------------------------------
    if item.arabic:
        rec = fetch_recitation(item, work) if item.kind == "quran" else None
        phases.append(("arabic", item.arabic, rec))
        info["audio"] = "Alafasy recitation" if rec else "none"

    # --- phase 2: Urdu translation + narration -----------------------------
    if item.urdu:
        if item.kind == "hadith" and has_isnad(item.urdu):
            # Narrating a chain of narrators is neither useful video nor safe to
            # auto-trim. The card shows the full verbatim text; the audio bed
            # carries it. A human narrator can be added later if desired.
            print("[video] this edition opens with a chain of narrators — "
                  "showing the full text on the card instead of auto-narrating it")
            phases.append(("urdu", item.urdu, None))
            info["narration"] = "skipped (isnad present)"
        else:
            nar = narrate_urdu(item.urdu, work / "urdu_narration.wav", engine=engine)
            phases.append(("urdu", item.urdu, nar))
            info["narration"] = engine

    # --- phase 3: optional English -----------------------------------------
    if include_english and item.english:
        phases.append(("english", item.english, None))

    segs: list[Path] = []
    for i, (kind, text, audio) in enumerate(phases):
        card = work / f"card_{i}_{kind}.png"
        kw = dict(size=(spec.width, spec.height), source=item.source,
                  source_ar=item.source_ar, topic=item.topic, theme=th)
        if kind == "arabic":
            kw["arabic"] = text
        elif kind == "urdu":
            # Urdu card = translation only. Repeating the Arabic here overflowed
            # the card and the Arabic has just had its own full-screen moment.
            kw["urdu"] = text
        else:
            kw["english"] = text
            kw["arabic"] = item.arabic  # keep the Arabic present for context
        write_card(card, **kw)

        if audio:
            dur = _dur(audio) + spec.hold_pad * 2
        else:
            # A silent card still has to be READ. Scale the hold to the amount
            # of text; a flat 5 s made a 700-character hadith impossible to read.
            chars = len(kw.get("arabic", "")) + len(kw.get("urdu", "")) \
                + len(kw.get("english", ""))
            dur = float(min(max(4.0 + chars / 38.0, 5.0), 24.0))
        seg = work / f"seg_{i}.mp4"
        _segment(card, audio, seg, spec, dur)
        segs.append(seg)
        info["segments"].append({"kind": kind, "seconds": round(_dur(seg), 2),
                                 "audio": "yes" if audio else "silent"})

    # --- concat ------------------------------------------------------------
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
          "-i", str(lst), "-c", "copy", str(out_path)])

    if add_backing:
        try:
            _add_backing(out_path, work)
            info["backing"] = "drone bed, ducked"
        except Exception as e:
            info["backing"] = f"skipped: {e}"

    info["file"] = str(out_path)
    info["duration"] = round(_dur(out_path), 2)
    info["size_mb"] = round(out_path.stat().st_size / 1e6, 2)
    return info


def _add_backing(video: Path, work: Path, gain: float = 0.18) -> None:
    """Quiet drone under the whole video, ducked beneath the voice."""
    from .cards import ROOT
    import sys
    sys.path.insert(0, str(ROOT))
    from naat.backing import BackingSpec, build_backing

    d = _dur(video)
    bed = work / "bed.wav"
    spec = BackingSpec(style="drone", root=110.0, intro=0.0, outro=0.0)
    sf.write(bed, build_backing(d, spec).astype(np.float32), SR)

    tmp = work / "final.mp4"
    # Does the assembled video actually carry an audio stream? A video made
    # entirely of silent cards has none, and a sidechain filter that references
    # [0:a] then fails — which is how the first hadith video ended up mute.
    has_audio = bool(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True).stdout.strip())

    if has_audio:
        fc = (f"[1:a]volume={gain}[bed];"
              f"[0:a][bed]sidechaincompress=threshold=0.06:ratio=8:attack=30:release=500[duck];"
              f"[0:a][duck]amix=inputs=2:duration=first:normalize=0[mix];"
              f"[mix]loudnorm=I=-16:TP=-1.5:LRA=11[out]")
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(bed),
              "-filter_complex", fc, "-map", "0:v", "-map", "[out]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
              "-ac", "2", str(tmp)])
    else:
        # Silent video: the bed becomes the audio track outright.
        _run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(bed),
              "-filter_complex", "[1:a]volume=0.30,loudnorm=I=-22:TP=-1.5:LRA=11[out]",
              "-map", "0:v", "-map", "[out]", "-c:v", "copy",
              "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
              "-shortest", str(tmp)])
    shutil.move(str(tmp), str(video))
