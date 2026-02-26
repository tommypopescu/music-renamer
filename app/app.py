import os
import subprocess
import logging
from flask import Flask, jsonify, render_template, request

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

def run_beet(args, timeout=3600):
    cmd = ["beet"] + args
    app.logger.info("Running: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.strip(), err.strip()

def inbox_path():
    return os.environ.get("MUSIC_INBOX", "/inbox")

@app.get("/")
def index():
    return render_template("index.html")

# ---------------------------------------------------------
# LOAD FILES INTO BEETS LIBRARY (NO TAGGING, NO MATCHING)
# ---------------------------------------------------------
@app.post("/api/load")
def api_load():
    path = inbox_path()
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": f"Inbox path does not exist: {path}"}), 400

    # Import WITHOUT tagging using -A
    code, out, err = run_beet(["import", "-A", path])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), (200 if code == 0 else 500)

# ---------------------------------------------------------
# CLEAN TITLES (remove leading numbers)
# ---------------------------------------------------------
@app.post("/api/clean-titles")
def api_clean_titles():
    code1, out1, err1 = run_beet([
        "modify", "-y",
        "title=^\\d+[-_\\. ]*(.*)$",
        "title=$1"
    ])
    if code1 != 0:
        return jsonify({"ok": False, "step": "modify", "stdout": out1, "stderr": err1}), 500

    code2, out2, err2 = run_beet(["move"])
    return jsonify({
        "ok": code2 == 0,
        "modify": out1 + "\n" + err1,
        "move": out2 + "\n" + err2
    }), (200 if code2 == 0 else 500)

# ---------------------------------------------------------
# PREVIEW / APPLY RENAME
# ---------------------------------------------------------
@app.post("/api/preview-rename")
def api_preview_rename():
    code, out, err = run_beet(["move", "-p"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500

@app.post("/api/apply-rename")
def api_apply_rename():
    code, out, err = run_beet(["move"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500

# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------
@app.post("/api/delete")
def api_delete():
    payload = request.get_json(force=True) or {}
    query = (payload.get("query") or "").strip()
    delete_files = bool(payload.get("delete_files", False))

    if not query:
        return jsonify({"ok": False, "error": "Query must not be empty."}), 400
    if query.startswith("-"):
        return jsonify({"ok": False, "error": "Query cannot start with '-'"}), 400

    args = ["remove", "-f"]
    if delete_files:
        args.append("-d")
    args.append(query)

    code, out, err = run_beet(args)
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500

@app.get("/api/config-paths")
def api_config_paths():
    return jsonify({
        "inbox": inbox_path(),
        "library": "/library",
        "config": "/config"
    })