#!/usr/bin/env python3
"""
Pull the published media back from GitHub Releases into web/video/.

Git holds the manifest and each clip's build record (the citation). The mp4s
and posters live in the GitHub Release named by each item's `release` field.
This is the bridge between the two, used in three places:

    python3 tools/fetch_media.py            # Pages deploy, or a local preview
    python3 tools/fetch_media.py --check    # weekly job: is every asset still there?
    python3 tools/fetch_media.py --clean    # delete the local copies again

No token: the repository is public, so release downloads are anonymous. A
download that comes back short, or not as an mp4/jpeg, is an error - a site
that silently serves a 404 page as a "video" is worse than one that fails to
deploy.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "video"
REPO = "zainkhan122/Quran"
MAGIC = {".mp4": (4, b"ftyp"), ".jpg": (0, b"\xff\xd8\xff")}


def url(tag: str, name: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def wanted() -> list[tuple[str, str, Path]]:
    """(release tag, asset name, local path) for every published file."""
    man = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    out = []
    for it in man.get("items", []):
        tag = it.get("release")
        if not tag:
            continue
        out.append((tag, it["file"], WEB / it["file"]))
        if it.get("poster"):
            out.append((tag, Path(it["poster"]).name, WEB / it["poster"]))
    return out


def looks_right(p: Path) -> bool:
    off, sig = MAGIC.get(p.suffix, (0, b""))
    with p.open("rb") as fh:
        head = fh.read(16)
    return head[off:off + len(sig)] == sig


def fetch(force: bool = False) -> int:
    bad = 0
    for tag, name, dest in wanted():
        if dest.exists() and not force and looks_right(dest):
            print(f"  have   {dest.relative_to(ROOT)}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url(tag, name), timeout=120) as r, \
                    tmp.open("wb") as fh:
                expect = int(r.headers.get("Content-Length") or 0)
                n = 0
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
                    n += len(chunk)
            if expect and n != expect:
                raise OSError(f"short read {n}/{expect}")
            if not looks_right(tmp):
                raise OSError("not the expected file type")
            tmp.replace(dest)
            print(f"  got    {dest.relative_to(ROOT)}  {n / 1e6:5.2f} MB  ({tag})")
        except (urllib.error.URLError, OSError) as e:
            tmp.unlink(missing_ok=True)
            print(f"  FAIL   {name} from {tag}: {e}", file=sys.stderr)
            bad += 1
    return bad


def check() -> int:
    bad = 0
    for tag, name, _ in wanted():
        req = urllib.request.Request(url(tag, name), method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                print(f"  ok     {tag}/{name}  {int(r.headers.get('Content-Length') or 0) / 1e6:5.2f} MB")
        except urllib.error.URLError as e:
            print(f"  GONE   {tag}/{name}: {e}", file=sys.stderr)
            bad += 1
    return bad


def clean() -> None:
    n = 0
    for p in [*WEB.glob("*.mp4"), *(WEB / "posters").glob("*.jpg")]:
        p.unlink()
        n += 1
    print(f"  removed {n} local media file(s); the manifest and citations stay")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="HEAD every asset, download nothing")
    ap.add_argument("--clean", action="store_true", help="delete local media copies")
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    a = ap.parse_args(argv)
    if a.clean:
        clean()
        return 0
    n = len(wanted())
    if not n:
        print("manifest names no release media - nothing to do")
        return 0
    bad = check() if a.check else fetch(a.force)
    print(f"\n{n - bad}/{n} asset(s) {'present' if a.check else 'in place'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
