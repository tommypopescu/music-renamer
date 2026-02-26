@app.post("/api/clean-titles")
def api_clean_titles():
    """
    Clean titles by removing leading numbers (01-, 001_, 1. etc).
    Then apply rename based on path templates.
    """
    # Remove leading numbers from title
    code1, out1, err1 = run_beet([
        "modify", "-y",
        "title=^\\d+[-_\\. ]*(.*)$",
        "title=$1"
    ])

    if code1 != 0:
        return jsonify({"ok": False, "step": "modify", "stdout": out1, "stderr": err1}), 500

    # Apply rename based on config paths (artist - title)
    code2, out2, err2 = run_beet(["move"])
    return jsonify({
        "ok": code2 == 0,
        "modify": out1 + "\n" + err1,
        "move": out2 + "\n" + err2
    }), (200 if code2 == 0 else 500)