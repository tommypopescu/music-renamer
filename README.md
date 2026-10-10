# Music Renamer (LAN‑only, no DB)

A minimal, containerized tool to **scan**, **manually edit** metadata (Artist/Title), and **rename audio files in‑place** using a configurable filename template.
No database, no external tag sources—just **fast, deterministic** operations on your local files.

## Key features

- **LAN‑only web UI** (Flask + Gunicorn)
- **Scan multiple inbox folders** recursively for audio files (configurable via `MUSIC_INBOXES`)
- **Editable table**: per‑row **Artist** and **Title** inputs
- **Per‑row checkbox**: choose exactly which tracks will be renamed
- **Inbox source column**: shows which source folder each file came from
- **Date/Time** column + **sort by newest first** (toggle on header)
- **Live “Preview name”** column that reflects edits in real time (no round‑trip)
- **Search/Filter**: Real-time filtering by filename, artist, or title
- **Preview rename** (server) with collision detection
- **Apply rename** in‑place (same folder as the original), with:
  - detailed JSON result (`moved`, `skipped`, `failed`)
  - automatic conflict resolution (`(1)`, `(2)`, …) if a file with the target name exists
- **Delete selected files**: Delete multiple files with individual confirmation for each file

> **Important**  
> This application **does not** write or change embedded tags. It only **renames the files** on disk, using either the filename heuristics or the values you manually edit in the UI.

---

## Architecture overview

```
Client (browser)
   ├─ Scan → /api/scan                # list files + parsed Artist/Title + mtime + inbox
   ├─ Live Preview name (client-side) # uses RENAME_TEMPLATE
   ├─ Preview rename → /api/preview   # server plan, marks collisions
   └─ Apply rename → /api/apply       # in-place rename, JSON report

Server (Flask)
   ├─ scan all paths in MUSIC_INBOXES (colon-separated)
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

| Variable | Default | Description |
|---|---|---|
| `MUSIC_INBOXES` | `/inbox` | **Colon-separated** list of absolute paths to scan. Example: `/inbox/1:/inbox/2:/inbox/3` |
| `MUSIC_INBOX` | `/inbox` | Legacy single-path fallback. Ignored when `MUSIC_INBOXES` is set. |
| `RENAME_TEMPLATE` | `{artist} - {title}` | Filename pattern used when renaming. |

> The rename is **in‑place**: destination is `file.parent / TEMPLATE.format(...) + ext`.  
> Files from different inbox folders are renamed within their own folder; they are **never moved across mounts**.

Examples for `RENAME_TEMPLATE`:
- `"{artist} - {title}"` → `Artist - Title.mp3`
- `"{artist}/{artist} - {title}"` → subfolder per artist (note: for in‑place you normally keep it flat)

---

## Run with Docker Compose

Mount each source folder to a **distinct sub-path** under `/inbox/` inside the container, then list all those paths in `MUSIC_INBOXES`:

```yaml
# compose.yaml
services:
  music-renamer:
    image: ghcr.io/tommypopescu/muserrenamer:latest
    container_name: music-renamer
    restart: unless-stopped
    environment:
      MUSIC_INBOXES: /inbox/1:/inbox/2:/inbox/3
      RENAME_TEMPLATE: "{artist} - {title}"
    volumes:
      - /mnt/music/complete:/inbox/1:rw
      - /mnt/music/club:/inbox/2:rw
      - /mnt/music/other:/inbox/3:rw
      - /mnt/music/library:/library:rw
    ports:
      - "8085:8080"
```

> **Rule:** every path listed in `MUSIC_INBOXES` **must** have a corresponding volume mount. Paths that don’t exist at startup are logged as warnings and skipped.

Then:

```bash
docker compose up -d
# UI: http://<HOST>:8085
```

### Single-folder (legacy) usage

If you only have one inbox folder, both old and new styles work:

```yaml
# old style (still supported)
environment:
  MUSIC_INBOX: /inbox
volumes:
  - /mnt/music:/inbox:rw

# new style (preferred)
environment:
  MUSIC_INBOXES: /inbox/1
volumes:
  - /mnt/music:/inbox/1:rw
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
   - Recursively lists audio files in **all** folders defined by `MUSIC_INBOXES` (`.mp3, .flac, .m4a, .ogg, .wav, .opus, .aac`).
   - For each file, **Artist** and **Title** are derived primarily from the filename (robust heuristic for ` - `, leading numbers, and trailing ` - www.domain.tld` tails).
   - If filename parsing fails completely, tags may be used as **fallback** (never override a successful filename parse).
   - Each row includes **Inbox** (source folder), **Date/Time** (last modification) and a **checkbox**.

2. **Search/Filter**
   - Use the search box to filter files by filename, artist, or title in real-time.
   - Filter stats show how many items match your search.
   - Click “Clear” to reset the filter.

3. **Manual edits**
   - You can override **Artist** and **Title** inline for any row.
   - The **Preview name** column updates **live** based on the current template and your edits.

4. **Sort by newest**
   - Click the **Date/Time** header to toggle descending/ascending by file mtime.
   - Default: newest first.

5. **Selection controls**
   - **Select all**: Select all visible (filtered) files
   - **Select none**: Deselect all files

6. **Preview rename**
   - Sends the current table state to the server.
   - Returns `src`, `dst`, and `collision` for selected rows.

7. **Apply rename**
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

8. **Delete selected files**
   - Each file prompts for individual confirmation before deletion.

---

## API reference (JSON)

> All endpoints return **JSON**, including error cases.

### `GET /api/settings`
Returns the current `RENAME_TEMPLATE` and configured `inboxes` list.

**Response**
```json
{ "ok": true, "template": "{artist} - {title}", "inboxes": ["/inbox/1", "/inbox/2"] }
```

### `POST /api/scan`
Scans **all** paths in `MUSIC_INBOXES` recursively and returns items.

**Response**
```json
{
  "ok": true,
  "items": [
    {
      "path": "/inbox/1/Artist - Title.mp3",
      "rel": "Artist - Title.mp3",
      "inbox": "/inbox/1",
      "artist": "Artist",
      "title": "Title",
      "ext": ".mp3",
      "selected": true,
      "mtime": 1772103036.68,
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
    { "src": "/inbox/1/file.mp3", "dst": "/inbox/1/Artist - Title.mp3", "collision": false, "missing": false }
  ]
}
```

### `POST /api/apply`
Apply in‑place renames for **selected** rows.

**Request**
```json
{ "items": [ { "path": "...", "artist": "...", "title": "...", "ext": ".mp3", "selected": true } ] }
```

**Response**
```json
{
  "ok": true,
  "moved":   [ { "from": "/inbox/1/a.mp3", "to": "/inbox/1/Artist - Title.mp3" } ],
  "skipped": [ { "path": "/inbox/2/same.mp3", "reason": "same name" } ],
  "failed":  [ { "path": "/inbox/1/bad.mp3", "error": "Permission denied" } ]
}
```

### `POST /api/delete`
Delete the given absolute paths.

**Request**
```json
{ "paths": ["/inbox/1/old.mp3", "/inbox/2/bad.flac"] }
```

**Response**
```json
{ "ok": true, "removed": ["/inbox/1/old.mp3"] }
```

---

## Filename rules and safety

- The final name is **exactly** what you type in **Artist/Title**, formatted with `RENAME_TEMPLATE`.  
- Only **forbidden filesystem characters** are sanitized: `\/ : * ? " < > |` → `_`.  
- Parentheses, quotes, dashes etc. are **preserved** exactly as edited.
- Files are **never moved between inbox folders**; the rename is strictly in‑place within the file’s own directory.

---

## Troubleshooting

### “Invalid JSON response” in the UI
```bash
docker logs --tail=200 music-renamer
```

Common causes:
- **Permission denied** on an inbox path → mount with `:rw`, ensure host folder permissions allow write.
- **Inbox directory not found** → check that every path in `MUSIC_INBOXES` has a matching volume mount. Missing dirs are logged as warnings and skipped.
- **Path missing** (file moved externally) → `failed: "source does not exist"`. Re‑scan and retry.
- **Same name** → appears in `skipped`.
- **Name collision** → server appends `(1)`, `(2)` automatically.

### Only one inbox folder shows up
Verify that `MUSIC_INBOXES` contains all paths separated by `:` **and** that each path has a volume mount:
```yaml
environment:
  MUSIC_INBOXES: /inbox/1:/inbox/2   # colon-separated
volumes:
  - /host/path/a:/inbox/1
  - /host/path/b:/inbox/2
```

### Preview shows correct target but file doesn’t change
- In `skipped` with `reason: "same name"` → file already has that name.
- In `failed` → see the `error` field and container logs.

---

## Develop locally (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

mkdir -p /tmp/inbox/1 /tmp/inbox/2
export MUSIC_INBOXES=/tmp/inbox/1:/tmp/inbox/2
export RENAME_TEMPLATE="{artist} - {title}"

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

- **Multiple inbox folders** via `MUSIC_INBOXES` (colon-separated); legacy `MUSIC_INBOX` still works
- **Inbox** column in scan results shows which source folder each file came from
- **Editable table** for `Artist` / `Title`
- **Checkbox** per row (rename only selected)
- **Date/Time** column with **sorting** (newest first toggle)
- **Search/Filter** functionality for real-time filtering by filename, artist, or title
- **Preview name** live in the UI based on `RENAME_TEMPLATE`
- **Preview** (server) returns collisions
- **Apply** (server) returns `moved/skipped/failed` and auto‑resolves name conflicts
- **Delete selected files** with individual confirmation for each file
- **Preserve exact edits** (no stripping parentheses/quotes at ends; only forbidden characters are replaced)

---

## License

Internal/demo use; choose a license that matches your distribution policy (e.g., MIT).

---

### Credits

- **Flask** web framework  
- **Mutagen** for tag reading (fallback only)
