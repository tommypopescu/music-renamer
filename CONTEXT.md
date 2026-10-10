# Music Renamer — Development Context

This document provides comprehensive context for developers and AI assistants
working on this project. Read this before making any changes.

---

## Project Overview

**Music Renamer** is a LAN-only web application for batch renaming audio files.
It provides a web UI for scanning, editing metadata, and renaming files **in-place**
(no tag writing, no external API, no database).

### Core Philosophy
- **No database** — all operations are stateless and file-based
- **In-place operations** — files are renamed within their original directory
- **Manual control** — user explicitly selects which files to process
- **Safety first** — confirmations, collision detection, detailed reporting
- **LAN only** — no authentication; expose only on trusted networks

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|--------|
| Backend | Python | 3.12 |
| Web framework | Flask | 3.1.3 |
| WSGI server | Gunicorn | 26.2.0 |
| Tag reading (fallback) | Mutagen | 1.47.0 |
| Frontend | Vanilla JS + HTML5 + CSS3 | — |
| Container base | `python:3.12-slim` (Debian 13) | — |
| Init process | tini | system |
| Deployment | Docker + Docker Compose | — |

---

## Project Structure

```
.
├── app/
│   ├── app.py                    # Flask backend (main application)
│   └── templates/
│       └── index.html            # Single-page UI (HTML + CSS + JS)
├── docker/
│   ├── Dockerfile                # Container image definition
│   └── entrypoint.sh             # Container startup script
├── .github/
│   ├── workflows/
│   │   └── build-push.yml        # CI/CD: build → push → Trivy → Cosign
│   └── dependabot.yml            # Auto-update GitHub Action versions
├── docs/
│   └── github-actions-cicd-guide.md  # Reutilizable CI/CD guide
├── beets/                        # (Optional) Beets config snippets
├── .trivyignore                  # CVE exceptions for Trivy scanner
├── compose.yaml                  # Docker Compose for OMV deployment
├── requirements.txt              # Python dependencies (all pinned)
├── CHANGELOG.md                  # Version history
├── CONTEXT.md                    # This file
└── README.md                     # User-facing documentation
```

---

## Key Files Deep Dive

### `app/app.py` (Backend)

**Environment variables read at startup**:

| Variable | Default | Description |
|----------|---------|-------------|
| `MUSIC_INBOXES` | `/inbox` | Colon-separated list of source folders |
| `MUSIC_INBOX` | `/inbox` | Legacy single-path fallback (ignored when `MUSIC_INBOXES` is set) |
| `RENAME_TEMPLATE` | `{artist} - {title}` | Filename pattern |

**Key globals**:
- `INBOXES: list[str]` — parsed from `MUSIC_INBOXES`
- `_INBOX_ROOTS: list[Path]` — resolved at startup, used by `_safe_path()`
- `TEMPLATE: str` — rename pattern

**Security helper — `_safe_path(raw: str) -> Path | None`**:
- Validates a user-supplied path by resolving it and checking it falls inside a
  known inbox root.
- **Reconstructs** the final path from `inbox_root` (trusted) + `rel` (verified
  relative suffix) — this breaks the tainted-data flow that CodeQL CWE-22 requires.
- Returns `None` for any path outside all inboxes.
- Used in: `/api/preview`, `/api/apply`, `/api/delete`.

**API Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Returns `template` + `inboxes` list |
| `POST` | `/api/scan` | Scans all INBOXES, returns file list |
| `POST` | `/api/preview` | Compute rename plan, mark collisions |
| `POST` | `/api/apply` | Execute in-place renames |
| `POST` | `/api/delete` | Delete specified files |

**Error handling pattern**: every exception is logged with
`app.logger.exception(...)` server-side; HTTP responses return only generic
messages (no `str(e)` exposure).

---

### `docker/Dockerfile`

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get upgrade -y   # pull all Debian security patches
RUN pip install --upgrade pip              # pip itself may have CVEs
COPY requirements.txt && pip install -r requirements.txt
# tini as PID 1 for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/entrypoint.sh"]
```

**Why `apt-get upgrade -y`**: the base `python:3.12-slim` image is not rebuilt
daily. Running `upgrade` pulls any OS-level security patches available at build
time, reducing the CVE surface that Trivy sees.

---

### `docker/entrypoint.sh`

```bash
_INBOXES="${MUSIC_INBOXES:-${MUSIC_INBOX:-/inbox}}"
IFS=':' read -ra _DIRS <<< "${_INBOXES}"
for _DIR in "${_DIRS[@]}"; do
  mkdir -p "${_DIR}"
done
mkdir -p /library
exec gunicorn -b 0.0.0.0:8080 app.app:app
```

Creates every inbox directory and `/library` at startup, then launches Gunicorn.

---

### `requirements.txt`

```
Flask==3.1.3
gunicorn==26.2.0
mutagen==1.47.0
# pinned to fix transitive CVEs
msgpack==1.2.1
setuptools==83.0.0
urllib3==2.8.0
```

The last three are **transitive dependencies** pinned explicitly to override
old versions that may appear in the dependency graph of other packages.

---

### `compose.yaml` (reference / example)

```yaml
services:
  music-renamer:
    image: ghcr.io/tommypopescu/muserrenamer:latest
    environment:
      MUSIC_INBOXES: /inbox/1:/inbox/2     # colon-separated
      RENAME_TEMPLATE: "{artist} - {title}"
    volumes:
      - ./data/config:/config
      - /host/path/complete:/inbox/1
      - /host/path/Muzica/Club:/inbox/2
      - /host/path/library:/library
    ports:
      - "8085:8080"
```

**Rule**: every path in `MUSIC_INBOXES` must have a matching volume mount.  
**Rule**: each mount must use a **distinct sub-path** (not the same `/inbox`).

---

### `.trivyignore`

Suppresses CVEs that Trivy reports but that have no actionable fix:
- **OS-level** (Debian 13): `util-linux`, `glibc`, `ncurses`, `systemd`,
  `sqlite`, etc. — `Status: affected`, no `Fixed Version`.
- **Python false positives**: `msgpack`, `setuptools`, `urllib3` CVEs
  detected from vendored metadata inside other packages. Actual installed
  versions are patched; these are not exploitable.

See `docs/github-actions-cicd-guide.md §5` for the full management policy.

---

### `.github/workflows/build-push.yml`

Full pipeline on every push to `main`:
1. `actions/checkout@v7`
2. `docker/login-action@v4` — GHCR auth via `GITHUB_TOKEN`
3. `docker/build-push-action@v7` — build + push `:latest` + `:sha`
4. `aquasecurity/trivy-action@v0.36.0` — blocking scan (CRITICAL+HIGH)
5. `aquasecurity/trivy-action@v0.36.0` — SARIF → Security tab
6. `github/codeql-action/upload-sarif@v4`
7. `sigstore/cosign-installer@v3` + `cosign sign` — keyless signing

See `docs/github-actions-cicd-guide.md` for the complete annotated template.

---

### `.github/dependabot.yml`

Weekly PRs for `github-actions` ecosystem. Merging strategy:
- Squash merge after checking compatibility score and release notes.
- Major version bumps: read the action's CHANGELOG for breaking changes first.

---

## Data Flow

### Scan
```
POST /api/scan
  for each inbox in INBOXES:
    rglob('*') → filter by SUPPORT_EXT
    parse_tags(path) → (artist, title)
    stat() → mtime
  return items[]
```

### Rename
```
POST /api/preview  ─→  validate paths (_safe_path), build target names
POST /api/apply    ─→  validate paths (_safe_path), os.replace() atomic rename
```

### Delete
```
POST /api/delete   ─→  validate paths (_safe_path), path.unlink()
```

---

## Supported Audio Formats

`.mp3` `.flac` `.m4a` `.ogg` `.wav` `.opus` `.aac`

---

## Filename Parsing Logic

`parse_tags()` in `app.py` uses this priority:

1. **Filename stem** → strip leading track numbers → strip trailing site tails
   (`- www.domain.com`) → split on ` - `.
2. **Embedded tags** (Mutagen) — only as fallback if step 1 yields nothing.
3. **Defaults**: `"Unknown Artist"` / `"Unknown Title"`.

Regex constants:
- `SITE_TAIL_RE` — matches trailing `- www.site.tld` patterns.
- `BAD_TAG_RE` — detects tag values that are URLs (reject as data).

---

## Common Development Tasks

### Add a new inbox
1. In `compose.yaml`: add a volume mount `/host/path:/inbox/N`.
2. In `compose.yaml`: append `:/inbox/N` to `MUSIC_INBOXES`.
3. `docker compose up -d` — no image rebuild needed.

### Add a new API endpoint
```python
@app.post("/api/newfeature")
def api_newfeature():
    try:
        payload = request.get_json(force=True) or {}
        # validate paths with _safe_path() if handling file paths
        return jsonify({"ok": True, "result": ...})
    except Exception:
        app.logger.exception("Fatal error in /api/newfeature")
        return jsonify({"ok": False, "error": "Operation failed."}), 500
```

### Update a CVE suppression
Edit `.trivyignore` — add a CVE ID and a comment with the date and reason.
Remove the entry once the upstream package ships a fix.

### Upgrade a dependency
1. Change the version in `requirements.txt`.
2. Push to `main` — the CI pipeline rebuilds the image and Trivy rescans.
3. If Trivy still reports the CVE: verify with `pip show PACKAGE` inside the
   new container.

---

## Debugging

```bash
# Container logs
docker logs --tail=200 music-renamer

# Shell inside container
docker exec -it music-renamer bash

# Check actual installed package versions
docker exec music-renamer pip show flask gunicorn setuptools

# Test API directly
curl -s -X POST http://HOST:8085/api/scan | python3 -m json.tool

# Verify Cosign signature
cosign verify ghcr.io/tommypopescu/muserrenamer:latest \
  --certificate-identity-regexp="https://github.com/tommypopescu/.*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

---

## Security Posture

| Control | Status | Detail |
|---------|--------|--------|
| Path traversal prevention | ✅ | `_safe_path()` reconstructs from trusted roots |
| Exception exposure | ✅ | Generic HTTP messages; full trace in server log only |
| Image vulnerability scan | ✅ | Trivy CRITICAL+HIGH blocks merge to main |
| Image signing | ✅ | Cosign keyless via GitHub OIDC + Rekor |
| Dependency updates | ✅ | Dependabot weekly PRs |
| OS patches at build time | ✅ | `apt-get upgrade -y` in Dockerfile |
| No authentication | ⚠️ | By design — LAN only; add reverse-proxy Basic Auth if needed |

---

## Testing Checklist

- [ ] Scan lists files from all configured inboxes
- [ ] Inbox column shows correct source folder per file
- [ ] Search filters by filename / artist / title
- [ ] Artist/Title edits update live preview
- [ ] Date/Time sort toggle works
- [ ] Preview shows correct target names and marks collisions
- [ ] Rename moves files in-place (same directory)
- [ ] Conflict resolution appends `(1)`, `(2)`
- [ ] Delete prompts per-file and removes only confirmed files
- [ ] Paths outside inbox are rejected (test with `../../../etc/passwd`)
- [ ] Dark mode renders correctly

---

## Quick Reference

| What | Where |
|------|-------|
| API endpoints | `app/app.py` |
| UI layout + JS | `app/templates/index.html` |
| Python deps | `requirements.txt` |
| Docker build | `docker/Dockerfile` |
| Container startup | `docker/entrypoint.sh` |
| Compose (OMV) | `compose.yaml` |
| CI/CD pipeline | `.github/workflows/build-push.yml` |
| CI/CD guide | `docs/github-actions-cicd-guide.md` |
| CVE suppressions | `.trivyignore` |
| Version history | `CHANGELOG.md` |
| User docs | `README.md` |

---

**Last updated**: 2026-10-10  
**Version**: 1.3.0
