import os
import subprocess
import logging
from flask import Flask, jsonify, render_template, request

# Logging pentru debugging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ---------- Utilities --------------------------------------------------------

def run_beet(args, timeout=3600):
    """
    Execute a beets CLI command and capture result.
    """
    cmd = ["beet"] + args
    app.logger.info("Running: %s", " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    out, err = proc.communicate(timeout=timeout)
    return proc.returncode, out.strip(), err.strip()


def inbox_path():
    return os.environ.get("MUSIC_INBOX", "/inbox")

# ---------- Routes -----------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")

# CLEAN TITLES (remove leading numbers such as 01-, 001_, 1.)
@app.post("/api/clean-titles")
def api_clean_titles():
    """
    Clean titles by removing leading numbers and separators.
    Example: '01 - Song.mp3' -> 'Song'
    """

    # Regex cleanup: ^digits + optional separators -> capture rest
    code1, out1, err1 = run_beet([
        "modify", "-y",
        "title=^\\d+[-_\\. ]*(.*)$",
        "title=$1"
    ])

    if code1 != 0:
        return jsonify({
            "ok": False,
            "step": "modify",
            "stdout": out1,
            "stderr": err1
        }), 500

    # Apply rename
    code2, out2, err2 = run_beet(["move"])

    return jsonify({
        "ok": code2 == 0,
        "modify": out1 + "\n" + err1,
        "move": out2 + "\n" + err2
    }), (200 if code2 == 0 else 500)


@app.post("/api/preview-rename")
def api_preview_rename():
    code, out, err = run_beet(["move", "-p"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500


@app.post("/api/apply-rename")
def api_apply_rename():
    code, out, err = run_beet(["move"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500


@app.post("/api/delete")
def api_delete():
    payload = request.get_json(force=True) or {}
    query = (payload.get("query") or "").strip()
    delete_files = bool(payload.get("delete_files", False))

    if not query:
        return jsonify({"ok": False, "error": "Query must not be empty."}), 400

    if query.startswith("-"):
        return jsonify({"ok": False, "error": "Query cannot start with '-'."}), 400

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


# OPTIONAL: mbsync (kept, but not needed for title cleaning flow)
@app.post("/api/update")
def api_update():
    code, out, err = run_beet(["mbsync"])
    return jsonify({"ok": code == 0, "stdout": out, "stderr": err}), 200 if code == 0 else 500