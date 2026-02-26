import os
import subprocess
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

def run_beet(args, timeout=3600):
    """
    Run a beets CLI command and return (exit_code, stdout, stderr).
    We prefer quiet mode where applicable to avoid interactive prompts.
    """
    cmd = ["beet"] + args
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.strip(), err.strip()

def inbox_path():
    # The incoming downloads folder is bind-mounted at /inbox.
    return os.environ.get("MUSIC_INBOX", "/inbox")

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/import")
def api_import():
    payload = request.get_json(silent=True) or {}
    path = payload.get("path") or inbox_path(
    code, out, err = run_beet(["-q", "import", path]) # type: ignore
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/update")
def api_update():
    code, out, err = run_beet(["-q", "mbsync"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/preview-rename")
def api_preview_rename():
    code, out, err = run_beet(["move", "-p"])  # -p = pretend / dry run
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/apply-rename")
def api_apply_rename():
    code, out, err = run_beet(["-q", "move"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.post("/api/delete")
def api_delete():
    payload = request.get_json(force=True) or {}
    query = (payload.get("query") or "").strip()
    delete_files = bool(payload.get("delete_files", False))
    if not query:
        return jsonify({"ok": False, "error": "Query must not be empty."}), 400

    args = ["remove", "-f"]
    if delete_files:
        args.append("-d")
    args.append(query)

    code, out, err = run_beet(args)
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

@app.get("/api/config-paths")
def api_config_paths():
    return jsonify({"inbox": inbox_path(), "library": "/library", "config": "/config"})
