#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Упрощённый HTTP-сервер для приёма Game State Integration от Dota 2.
• Логирует каждый POST-пакет в ./gsi_logs/UTC-метка.json
• Печатает IP источника, размер пакета и текущий game_clock
"""

from flask import Flask, request, abort
from pathlib import Path
from datetime import datetime
import json

app = Flask(__name__)
LOG_DIR = Path("gsi_logs")
LOG_DIR.mkdir(exist_ok=True)

@app.route("/gsi", methods=["POST"])
def handle_gsi():
    if not request.is_json:
        abort(400, "Need JSON")

    payload = request.get_json(force=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    (LOG_DIR / f"{ts}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    map_time = payload.get("map", {}).get("clock_time")
    print(
        f"[{ts}] {request.remote_addr}:{request.environ.get('REMOTE_PORT')} "
        f"{len(request.data)} bytes   map_time={map_time}"
    )
    return "OK", 200


if __name__ == "__main__":
    # 0.0.0.0 → слушаем и localhost, и 192.168.x.x
    app.run(host="0.0.0.0", port=5000, threaded=True)
