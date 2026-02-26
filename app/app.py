import os
import re
import shutil
import logging
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from mutagen import File as MutaFile

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

SUPPORT_EXT = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus", ".aac"}

INBOX = os.environ.get("MUSIC_INBOX", "/inbox")
OUTDIR = os.environ.get("MUSIC_OUTDIR", "/library")  # could be same as INBOX for in-place
TEMPLATE = os.environ.get("RENAME_TEMPLATE", "{artist} - {title}")

def list_audio_files(root: str):
    rootp = Path(root)
    for p in sorted(rootp.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORT_EXT:
            yield p

def parse_tags(path: Path):
    """Return (artist,title) using tags if any; else heuristics from filename."""
    try:
        mf = MutaFile(str(path))
    except Exception:
        mf = None

    artist = title = ""

    if mf:
        # Try common tag keys
        for key in ("artist", "ARTIST", "\xa9ART", "TPE1"):
            v = mf.tags.get(key) if getattr(mf, "tags", None) else None
            if v:
                artist = str(v[0] if isinstance(v, list) else v)
                break
        for key in ("title", "TITLE", "\xa9nam", "TIT2"):
            v = mf.tags.get(key) if getattr(mf, "tags", None) else None
            if v:
                title = str(v[0] if isinstance(v, list) else v)
                break

    if not artist or not title:
        base = path.stem
        # Common pattern: "01 - Artist - Title", "Artist - 01 - Title", "01 Title"
        # 1) strip leading track numbers & separators
        base = re.sub(r"^\s*\d+\s*[-_. ]\s*", "", base).strip()
        # 2) try split "Artist - Title"
        parts = re.split(r"\s*-\s*", base, maxsplit=1)
        if len(parts) == 2:
            cand_artist, cand_title = parts
            artist = artist or cand_artist.strip()
            title = title or cand_title.strip()
        else:
            # fallback: everything is title
            title = title or base.strip()

    # Final cleanup: remove any remaining leading numbers in title
    title = re.sub(r"^\d+[-_. ]*", "", title).strip()
    return artist or "Unknown Artist", title or "Unknown Title"

def build_target(artist: str, title: str, ext: str):
    safe_artist = artist.strip()
    safe_title  = title.strip()
    name = TEMPLATE.format(artist=safe_artist, title=safe_title).strip()
    # basic sanitization
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return f"{name}{ext.lower()}"

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/scan")
def api_scan():
    items = []
    for p in list_audio_files(INBOX):
        artist, title = parse_tags(p)
        items.append({
            "path": str(p),
            "rel": str(p.relative_to(INBOX)),
            "artist": artist,
            "title": title,
            "ext": p.suffix.lower(),
        })
    return jsonify({"ok": True, "items": items})

@app.post("/api/preview")
def api_preview():
    dest_base = Path(OUTDIR)
    preview = []
    for p in list_audio_files(INBOX):
        artist, title = parse_tags(p)
        target_name = build_target(artist, title, p.suffix)
        target_path = dest_base / target_name
        preview.append({"src": str(p), "dst": str(target_path)})
    return jsonify({"ok": True, "preview": preview})

@app.post("/api/apply")
def api_apply():
    dest_base = Path(OUTDIR)
    dest_base.mkdir(parents=True, exist_ok=True)
    ops = []
    for p in list_audio_files(INBOX):
        artist, title = parse_tags(p)
        target_name = build_target(artist, title, p.suffix)
        dst = dest_base / target_name
        # If same dir and same path, skip
        if p.resolve() == dst.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        # move (rename across fs if needed)
        shutil.move(str(p), str(dst))
        ops.append({"from": str(p), "to": str(dst)})
    return jsonify({"ok": True, "moved": ops})

@app.post("/api/delete")
def api_delete():
    payload = request.get_json(force=True) or {}
    paths = payload.get("paths") or []
    removed = []
    for s in paths:
        p = Path(s)
        if p.exists() and p.is_file():
            p.unlink()
            removed.append(s)
    return jsonify({"ok": True, "removed": removed})