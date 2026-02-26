import os
import re
import shutil
import logging
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from mutagen import File as MutaFile

# -----------------------------------------------------------------------------
# App & logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# -----------------------------------------------------------------------------
# Settings (via ENV)
# -----------------------------------------------------------------------------
SUPPORT_EXT = {".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus", ".aac"}

INBOX = os.environ.get("MUSIC_INBOX", "/inbox")          # source folder
OUTDIR = os.environ.get("MUSIC_OUTDIR", "/library")       # target folder; can be /inbox for in-place
TEMPLATE = os.environ.get("RENAME_TEMPLATE", "{artist} - {title}")

# -----------------------------------------------------------------------------
# Regex helpers: remove trailing site tails; detect spammy tag values
# -----------------------------------------------------------------------------
SITE_TAIL_RE = re.compile(
    r"""\s*[-–—]\s*                 # a dash separator
        (?:www\.)?                  # optional www.
        [a-z0-9][a-z0-9.-]*\.(?:com|net|org|info|biz|ro|de|fr|it|es|uk)
        (?:\b.*)?                   # optional tail
    """,
    re.IGNORECASE | re.VERBOSE,
)

BAD_TAG_RE = re.compile(r"(?:www\.|https?://|\.com\b|\.net\b|\.org\b)", re.IGNORECASE)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def list_audio_files(root: str):
    """Yield audio files (by extension) recursively from root."""
    rootp = Path(root)
    for p in sorted(rootp.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORT_EXT:
            yield p

def _clean_base_from_filename(path: Path) -> str:
    """
    Take filename stem and remove:
      1) leading track numbers + separators: '01 - ', '001_', '1.', '03   '
      2) trailing 'site tails': ' - www.something.com' etc.
      3) double spaces
    """
    base = path.stem
    base = re.sub(r"^\s*\d+\s*[-_. ]\s*", "", base)
    base = SITE_TAIL_RE.sub("", base).strip()
    base = re.sub(r"\s{2,}", " ", base).strip()
    return base

def _split_artist_title_from_base(base: str) -> tuple[str, str]:
    """
    Split a cleaned base string by ' - ' (any dash with optional spaces).
    If we get >=2 parts: artist = first, title = last; otherwise title=base.
    Also normalizes strange dashes and trims quotes/brackets.
    """
    norm = re.sub(r"[–—]", "-", base)  # normalize em/en dashes to '-'
    parts = [p.strip() for p in re.split(r"\s*-\s*", norm) if p.strip()]
    if len(parts) >= 2:
        artist = parts[0]
        title = parts[-1]
    else:
        artist, title = "", parts[0] if parts else ""

    # Safety: remove any trailing site tail from title and trim junk chars
    title = SITE_TAIL_RE.sub("", title).strip().strip(" '\"-–—_")
    artist = artist.strip().strip(" '\"-–—_")
    return artist, title

def _safe_tag_text(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)) and v:
        return str(v[0])
    return str(v)

def parse_tags(path: Path) -> tuple[str, str]:
    """
    Robust artist/title detection:
      - derive FIRST from filename (handles site tails + numbers + multiple dashes)
      - use tags ONLY IF they look clean (no www/http/.com etc.)
    """
    # 1) filename-derived
    base = _clean_base_from_filename(path)
    fn_artist, fn_title = _split_artist_title_from_base(base)

    artist = fn_artist or "Unknown Artist"
    title  = fn_title or "Unknown Title"

    # 2) attempt tags (accept only if they aren't 'site-like')
    tag_artist = tag_title = ""
    try:
        mf = MutaFile(str(path))
        if mf and getattr(mf, "tags", None):
            for key in ("artist", "ARTIST", "\xa9ART", "TPE1"):
                val = _safe_tag_text(mf.tags.get(key))
                if val:
                    tag_artist = val.strip()
                    break
            for key in ("title", "TITLE", "\xa9nam", "TIT2"):
                val = _safe_tag_text(mf.tags.get(key))
                if val:
                    tag_title = val.strip()
                    break
    except Exception:
        pass

    if tag_artist and not BAD_TAG_RE.search(tag_artist):
        artist = tag_artist
    if tag_title and not BAD_TAG_RE.search(tag_title):
        title = SITE_TAIL_RE.sub("", tag_title).strip().strip(" '\"-–—_")

    # Final normalization
    artist = re.sub(r"\s{2,}", " ", artist).strip() or "Unknown Artist"
    title  = re.sub(r"\s{2,}", " ", title).strip()  or "Unknown Title"
    return artist, title

def build_target(artist: str, title: str, ext: str) -> str:
    """Return final file name according to template and sanitize it."""
    safe_artist = artist.strip()
    safe_title  = title.strip()
    name = TEMPLATE.format(artist=safe_artist, title=safe_title).strip()
    name = name.strip(" '\"-–—_")
    # sanitize filename
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return f"{name}{ext.lower()}"

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/scan")
def api_scan():
    """List audio items found in /inbox with detected artist/title."""
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
    """
    Use manual edits if provided.
    Body: { items: [ {path, artist, title, ext}, ... ] }
    """
    payload = request.get_json(force=True) or {}
    items = payload.get("items") or []

    preview = []
    for it in items:
        p = Path(it["path"])
        artist = it.get("artist") or "Unknown Artist"
        title  = it.get("title")  or "Unknown Title"
        ext    = it.get("ext")    or p.suffix.lower()

        target_name = build_target(artist, title, ext)
        target_path = Path(OUTDIR) / target_name

        preview.append({ "src": str(p), "dst": str(target_path) })

    return jsonify({"ok": True, "preview": preview})

@app.post("/api/apply")
def api_apply():
    payload = request.get_json(force=True) or {}
    items = payload.get("items") or []

    dest = Path(OUTDIR)
    dest.mkdir(parents=True, exist_ok=True)

    moved = []

    for it in items:
        p = Path(it["path"])
        if not p.exists():
            continue

        artist = it.get("artist") or "Unknown Artist"
        title  = it.get("title")  or "Unknown Title"
        ext    = it.get("ext")    or p.suffix.lower()

        target_name = build_target(artist, title, ext)
        dst = dest / target_name

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dst))
        moved.append({"from": str(p), "to": str(dst)})

    return jsonify({"ok": True, "moved": moved})

@app.post("/api/delete")
def api_delete():
    """Delete selected absolute file paths (one per line from UI)."""
    payload = request.get_json(force=True) or {}
    paths = payload.get("paths") or []
    removed = []
    for s in paths:
        p = Path(s)
        if p.exists() and p.is_file():
            p.unlink()
            removed.append(s)
    return jsonify({"ok": True, "removed": removed})