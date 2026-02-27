# Music Renamer (LAN‑only, no DB)

A minimal, containerized tool to **scan**, **manually edit** metadata (Artist/Title), and **rename audio files in‑place** using a configurable filename template.
No database, no external tag sources—just **fast, deterministic** operations on your local files.

## Key features

- **LAN‑only web UI** (Flask + Gunicorn)
- **Scan** a folder recursively (default: `/inbox`) for audio files
- **Editable table**: per‑row **Artist** and **Title** inputs
- **Per‑row checkbox**: choose exactly which tracks will be renamed
- **Date/Time** column + **sort by newest first** (toggle on header)
- **Live “Preview name”** column that reflects edits in real time (no round‑trip)
- **Preview rename** (server) with collision detection
- **Apply rename** in‑place (same folder as the original), with:
  - detailed JSON result (`moved`, `skipped`, `failed`)
  - automatic conflict resolution (`(1)`, `(2)`, …) if a file with the target name exists
- **Delete** utility for one‑off cleanup (paste absolute paths)

> **Important**  
> This application **does not** write or change embedded tags. It only **renames the files** on disk, using either the filename heuristics or the values you manually edit in the UI.

---

## Architecture overview

```
Client (browser)
   ├─ Scan → /api/scan                # list files + parsed Artist/Title + mtime
   ├─ Live Preview name (client-side) # uses RENAME_TEMPLATE
   ├─ Preview rename → /api/preview   # server plan, marks collisions
   └─ Apply rename → /api/apply       # in-place rename, JSON report

Server (Flask)
   ├─ parse from filename (robust dashes/numbers/site tails)
   ├─ optional fallback from tags if filename parsing failed
   ├─ never strips your manual edits (keeps parentheses etc.)
   ├─ sanitize only forbidden filesystem chars \/:*?"<>|
   └─ rename in-place using os.replace (atomic within the same folder)
```

---

## Requirements

- **Docker** & **Docker Compose** (recommended)  
- Or, locally: **Python 3.12+** with:
  - `Flask`
  - `gunicorn`
  - `mutagen`

### `requirements.txt`

```txt
Flask==3.0.2
gunicorn==21.2.0
mutagen==1.47.0
```

---

## Configuration

The app uses environment variables (see Compose snippet below):

- `MUSIC_INBOX` — folder to scan (default: `/inbox`)
- `RENAME_TEMPLATE` — filename pattern (default: `"{artist} - {title}"`)

> The rename is **in‑place**: destination is `file.parent / TEMPLATE.format(...) + ext`.

Examples for `RENAME_TEMPLATE`:
- `"{artist} - {title}"` → `Artist - Title.mp3`
- `"{artist}/{artist} - {title}"` → subfolder per artist (note: for in‑place you normally keep it flat)

---

## Run with Docker Compose

Create host folders and map them into the container. For in‑place rename, map your music root to `/inbox`:

```yaml
# compose.yaml
services:
  music-renamer:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: music-renamer
    restart: unless-stopped
    environment:
      MUSIC_INBOX: /inbox
      RENAME_TEMPLATE: "{artist} - {title}"
    volumes:
      - /mnt/music-inbox:/inbox:rw
    ports:
      - "8080:8080"
```

Then:

```bash
docker compose up -d --build
# UI: http://<HOST>:8080
```

---

## Folder structure (suggested)

```
.
├─ app/
│  ├─ app.py                  # Flask backend
│  └─ templates/
│     └─ index.html           # Editable UI
├─ docker/
│  ├─ Dockerfile
│  └─ entrypoint.sh
├─ requirements.txt
└─ README.md
```

---

## UI workflow

1. **Scan**  
   - Recursively lists audio files in `/inbox` (`.mp3, .flac, .m4a, .ogg, .wav, .opus, .aac`).
   - For each file, **Artist** and **Title** are derived primarily from the filename (robust heuristic for ` - `, leading numbers, and trailing ` - www.domain.tld` tails).  
   - If filename parsing fails completely, tags may be used as **fallback** (never override a successful filename parse).
   - Each row includes **Date/Time** (last modification) and a **checkbox** (selected by default).

2. **Manual edits**  
   - You can override **Artist** and **Title** inline for any row.  
   - The **Preview name** column updates **live** based on the current template and your edits.

3. **Sort by newest**  
   - Click the **Date/Time** header to toggle descending/ascending by file mtime.  
   - Default: newest first.

4. **Preview rename**  
   - Sends the current table state to the server.  
   - Returns `src`, `dst`, and `collision` for selected rows (if a file with the target name already exists).

5. **Apply rename**  
   - Sends the current table state to the server.  
   - Performs **in‑place** rename using `os.replace` (atomic within same folder).  
   - If `dst` exists and is a different file, the server finds a free name by appending `(1)`, `(2)`, etc.  
   - Server responds with a JSON report:
     ```json
     {
       "ok": true,
       "moved":   [ {"from": "...", "to": "..."} ],
       "skipped": [ {"path": "...", "reason": "not selected|same name"} ],
       "failed":  [ {"path": "...", "error": "message"} ]
     }
     ```

6. **Delete** (utility)  
   - Paste absolute paths (one per line) to delete files.

---

## API reference (JSON)

> All endpoints return **JSON**, including error cases.

### `GET /api/settings`
Returns the current `RENAME_TEMPLATE` for the UI.

**Response**
```json
{ "ok": true, "template": "{artist} - {title}" }
```

### `POST /api/scan`
Scans `MUSIC_INBOX` recursively and returns items.

**Response**
```json
{
  "ok": true,
  "items": [
    {
      "path": "/inbox/Artist - Title.mp3",
      "rel": "Artist - Title.mp3",
      "artist": "Artist",
      "title": "Title",
      "ext": ".mp3",
      "selected": true,
      "mtime": 1772103036.6767256,
      "mtime_str": "2026-02-26 10:50:36"
    }
  ]
}
```

### `POST /api/preview`
Compute planned renames in‑place for **selected** rows.

**Request**
```json
{ "items": [ { "path": "...", "artist": "...", "title": "...", "ext": ".mp3", "selected": true } ] }
```

**Response**
```json
{
  "ok": true,
  "preview": [
    { "src": "/inbox/file.mp3", "dst": "/inbox/Artist - Title.mp3", "collision": false, "missing": false }
  ]
}
```

### `POST /api/apply`
Apply in‑place renames for **selected** rows. Always returns JSON with details.

**Request**
```json
{ "items": [ { "path": "...", "artist": "...", "title": "...", "ext": ".mp3", "selected": true } ] }
```

**Response**
```json
{
  "ok": true,
  "moved":   [ { "from": "/inbox/a.mp3", "to": "/inbox/Artist - Title.mp3" } ],
  "skipped": [ { "path": "/inbox/same.mp3", "reason": "same name" } ],
  "failed":  [ { "path": "/inbox/bad.mp3", "error": "Permission denied" } ]
}
```

### `POST /api/delete`
Delete the given absolute paths (one per line pasted in the UI).

**Request**
```json
{ "paths": ["/inbox/old.mp3", "/inbox/bad.flac"] }
```

**Response**
```json
{ "ok": true, "removed": ["/inbox/old.mp3"] }
```

---

## Filename rules and safety

- The final name is **exactly** what you type in **Artist/Title**, formatted with `RENAME_TEMPLATE`.  
- We only sanitize **forbidden filesystem characters**: `\/ : * ? " < > |` → `_` (cross‑platform consistency).  
- Parentheses, quotes, dashes etc. are **preserved** exactly as edited.

---

## Troubleshooting

### “Invalid JSON response” in the UI
The server always returns JSON; if you see this, likely a Python exception occurred **before** our handler returned.  
Run:

```bash
docker logs --tail=200 music-renamer
```

Common causes and fixes:
- **Permission denied** on `/inbox` → mount with `:rw`, ensure host folder permissions allow write (`chown/chmod` as needed).
- **Path missing** (file moved externally) → `failed: "source does not exist"`. Re‑scan and retry.
- **Same name** → nothing to change; appears in `skipped`.
- **Name collision** → server appends `(1)`, `(2)` automatically.

### Sorting not applied
Click the **Date/Time** header. Arrow `▼` means **newest first** (descending), `▲` means oldest first.

### Preview shows correct target but file doesn’t change
Check the **Apply** response:
- If it’s in `skipped` with `reason: "same name"`, the file already has that name.
- If it’s in `failed`, see the `error` field and container logs.

---

## Develop locally (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

# required folders
mkdir -p /tmp/inbox
export MUSIC_INBOX=/tmp/inbox
export RENAME_TEMPLATE="{artist} - {title}"

# run dev server
FLASK_APP=app/app.py flask run -p 8080
# or production-like
gunicorn -b 0.0.0.0:8080 app.app:app
```

Open `http://localhost:8080`.

---

## Security notes (LAN only)

- The application is **not authenticated**—expose it only on **trusted LAN segments**.  
- Consider securing via reverse proxy (Basic Auth) or Docker network restrictions if needed.  
- The Delete endpoint accepts absolute paths—users with UI access can remove files. Keep UI access limited.

---

## Change log (functional highlights)

- **Editable table** for `Artist` / `Title`
- **Checkbox** per row (rename only selected)
- **Date/Time** column with **sorting** (newest first toggle)
- **Preview name** live in the UI based on `RENAME_TEMPLATE`
- **Preview** (server) returns collisions
- **Apply** (server) returns `moved/skipped/failed` and auto‑resolves name conflicts
- **Preserve exact edits** (no stripping parentheses/quotes at ends; only forbidden characters are replaced)

---

## License

Internal/demo use; choose a license that matches your distribution policy (e.g., MIT).

---

### Credits

- **Flask** web framework  
- **Mutagen** for tag reading (fallback only)
