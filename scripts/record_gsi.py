#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
record_gsi.py — standalone debug recorder for Dota 2 GSI packets.

Logs every POST to ./gsi_logs/ as a timestamped JSON file.
Runs on port 5001 to avoid conflicts with the main runtime server.

Usage:
    python scripts/record_gsi.py
"""

from flask import Flask, request, abort
from pathlib import Path
from datetime import datetime, UTC
import json

app = Flask(__name__)
LOG_DIR = Path("gsi_logs")
LOG_DIR.mkdir(exist_ok=True)


@app.route("/gsi", methods=["POST"])
def handle_gsi():
    if not request.is_json:
        abort(400, "Need JSON")

    payload = request.get_json(force=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    (LOG_DIR / f"{ts}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    map_time = payload.get("map", {}).get("clock_time")
    print(f"[{ts}] {request.remote_addr} | {len(request.data)} bytes | clock={map_time}")
    return "OK", 200


if __name__ == "__main__":
    print("✓ GSI recorder starting on port 5001 (debug utility)")
    app.run(host="0.0.0.0", port=5001, threaded=True)
