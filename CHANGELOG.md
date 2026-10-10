# Changelog

All notable changes to this project are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [1.3.0] — 2026-10-10

### Added
- **Multi-inbox support** (`MUSIC_INBOXES`): container now accepts any number of
  source folders, separated by colons (e.g. `MUSIC_INBOXES=/inbox/1:/inbox/2:/inbox/3`).
  Legacy `MUSIC_INBOX` still works as a single-path fallback.
- **Inbox column** in scan results: UI now shows which source folder each file came from.
- **`/api/settings`** endpoint exposes the full `inboxes` list to the UI.
- **`_safe_path()` helper** in `app.py`: path traversal prevention. Every user-supplied
  path is resolved, checked against known inbox roots, then **reconstructed** from trusted
  components only — breaking the tainted-data flow that CodeQL flagged.
- **`CHANGELOG.md`** (this file).
- **`docs/github-actions-cicd-guide.md`**: reutilizable CI/CD guide for future projects.
- **`.github/dependabot.yml`**: weekly automatic dependency updates for GitHub Actions.
- **Trivy scanning** in CI (`aquasecurity/trivy-action@v0.36.0`):
  - blocking scan (CRITICAL + HIGH → `exit-code: 1`, table format)
  - SARIF upload to GitHub Security tab (non-blocking, `if: always()`)
- **Cosign keyless image signing** via GitHub OIDC (`sigstore/cosign-installer@v3`).
- **CodeQL SARIF upload** upgraded to `github/codeql-action/upload-sarif@v4`.
- **`.trivyignore`**: suppresses CVEs with no available fix:
  - OS-level CVEs in Debian 13 (glibc, util-linux, ncurses, systemd, sqlite, etc.)
  - Python transitive-dep false positives (msgpack, setuptools, urllib3) detected
    from vendored metadata inside other packages; fixed versions are installed.

### Changed
- **`compose.yaml`**: migrated to `MUSIC_INBOXES`, volumes now mount to `/inbox/1`,
  `/inbox/2` (distinct sub-paths); removed invalid duplicate `/inbox` mounts.
- **`entrypoint.sh`**: now iterates all paths in `MUSIC_INBOXES` and runs `mkdir -p`
  for each, plus `/library`.
- **`Flask`** pinned to `3.1.3` (was `3.0.2`).
- **`gunicorn`** pinned to `26.2.0` (was `21.2.0`).
- **`pip`** upgraded inside Dockerfile (`--upgrade pip`) before installing deps.
- **`apt-get upgrade -y`** added to Dockerfile to pull latest Debian security patches.
- **GitHub Actions versions** bumped:
  - `actions/checkout` v4 → v7
  - `docker/login-action` v3 → v4
  - `docker/build-push-action` v6 → v7

### Removed
- **`beets`** dependency removed from the container image — it was unused and
  introduced several high-severity CVEs.

### Security
- **Path traversal (CodeQL CWE-22)**: all 16 `Path(it["path"])` usages in
  `/api/preview`, `/api/apply`, `/api/delete` replaced with `_safe_path()` which
  validates + reconstructs paths from trusted inbox roots.
- **Exception exposure**: `str(e)` in HTTP error responses replaced with generic
  messages; full stack traces logged server-side only (`app.logger.exception`).
- **Transitive CVEs fixed**: `msgpack==1.2.1`, `setuptools==83.0.0`,
  `urllib3==2.8.0` explicitly pinned in `requirements.txt` and installed
  in the correct order in Dockerfile.

---

## [1.2.0] — 2026-04-10

### Added
- **Delete selected files**: Delete multiple files from the UI with individual
  per-file confirmation dialogs.
- **Search/Filter**: Real-time filtering by filename, artist, or title with
  filter stats display.
- **Date/Time column** with sortable mtime (newest-first toggle).
- **Select all / Select none** buttons for visible (filtered) rows.

### Changed
- Filename parsing now prioritises filename over embedded tags in all cases.
- `RENAME_TEMPLATE` is now fetched from `/api/settings` and used for live preview.

---

## [1.1.0] — initial

### Added
- LAN-only Flask + Gunicorn web application.
- Scan inbox folder recursively for audio files.
- Editable Artist/Title table with live preview column.
- Per-row checkbox for selective rename.
- Preview + Apply rename with collision detection and auto-resolution `(1)`, `(2)`.
- Single-path `MUSIC_INBOX` and `RENAME_TEMPLATE` configuration via env vars.
- Docker container with `tini` init process.
