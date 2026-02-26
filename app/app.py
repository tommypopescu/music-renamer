import os
import subprocess
import logging
from flask import Flask, jsonify, render_template, request

# Configure simple logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ---------- Utilities --------------------------------------------------------
def run_beet(args, timeout=3600):
    """
    Run a beets CLI command and return (exit_code, stdout, stderr).
    We prefer quiet mode where applicable to avoid interactive prompts.
    """
    cmd = ["beet"] + args
    app.logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.strip(), err.strip()

def inbox_path():
    # The incoming downloads folder is bind-mounted at /inbox.
    return os.environ.get("MUSIC_INBOX", "/inbox")

# ---------- Routes -----------------------------------------------------------
@app.get("/")
def index():
    # Render a minimal, LAN-only UI with action buttons.
    return render_template("index.html")

@app.post("/api/import")
def api_import():
    """
    Import & autotag everything from the inbox folder in quiet mode.
    'quiet_fallback: asis' from config ensures unattended behavior.
    Falls back to /inbox when no path is provided or path is empty/None.
    """
    payload = request.get_json(silent=True) or {}
    path = payload.get("path") or inbox_path()
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": f"Inbox path does not exist: {path}"}), 400
    code, out, err = run_beet(["import", path])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/update")
def api_update():
    """
    Refresh metadata from MusicBrainz for the entire library using mbsync.
    Requires the 'mbsync' plugin enabled in config.
    """
    code, out, err = run_beet(["mbsync"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/preview-rename")
def api_preview_rename():
    """
    Show a dry-run of moves/renames according to current path templates.
    """
    code, out, err = run_beet(["move", "-p"])  # -p = pretend / dry run
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/apply-rename")
def api_apply_rename():
    """
    Apply renames/moves to match the configured path templates.
    """
    code, out, err = run_beet(["move"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/delete")
def api_delete():
    """
    Delete items from the beets library using a beets query.
    If 'delete_files' is true, files will be removed from disk (-d).
    We pass -f to skip confirmation (LAN-only, admin-only UI).
    """
    payload = request.get_json(force=True) or {}
    query = (payload.get("query") or "").strip()
    delete_files = bool(payload.get("delete_files", False))
    if not query:
        return jsonify({"ok": False, "error": "Query must not be empty."}), 400

    # Safety: disallow options being injected as the first token
    if query.startswith("-"):
        return jsonify({"ok": False, "error": "Query must not start with '-' (options are not allowed)."}), 400

    args = ["remove", "-f"]
    if delete_files:
        args.append("-d")
    args.append(query)

    code, out, err = run_beet(args)
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.get("/api/config-paths")
def api_config_paths():
    # Return container-visible paths for client hints.
    return jsonify({"inbox": inbox_path(), "library": "/library", "config": "/config"})