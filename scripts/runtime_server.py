#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runtime_server.py — Aegis Assistant live runtime.

Responsibilities:
  • Accept Dota 2 GSI packets (POST /gsi)
  • Extract 12 game-state features from live data
  • Query the model API for a macro-action prediction
  • Serve the current hint for the overlay (GET /hint)
  • Health / debug endpoints

Endpoints:
  POST /gsi            — Dota 2 Game State Integration receiver
  GET  /hint           — current hint (for overlay polling)
  GET  /health         — server and model API health
  GET  /debug/state    — raw last GSI payload
  GET  /debug/features — last computed feature vector

Usage:
    python scripts/runtime_server.py
    python scripts/runtime_server.py --capture-minimap   # experimental
"""

from __future__ import annotations

import argparse
import collections
import json
import threading
import time
from datetime import datetime, UTC
from pathlib import Path

import requests as http_requests
from flask import Flask, request, jsonify, abort
from flask_cors import CORS

from config import LABEL2TXT, MODEL_API_URL

# ═══════════════════════════════════════════════════════════════════════════ #
#   APP SETUP
# ═══════════════════════════════════════════════════════════════════════════ #

app = Flask(__name__)
CORS(app)

LOG_DIR = Path("gsi_logs")
LOG_DIR.mkdir(exist_ok=True)

# ─── Shared mutable state (protected by LOCK) ────────────────────────────── #
LOCK = threading.Lock()

STATE: dict = {}                         # latest raw GSI snapshot
HINT: str = "Waiting for game data…"
HINT_ACTION: str = ""
HINT_CONFIDENCE: float = 0.0
LAST_GSI_TS: int = 0                     # epoch of last GSI packet
LAST_FEATURES: dict = {}                 # last computed feature vector
GSI_COUNT: int = 0                       # total GSI packets received
CURRENT_MATCH_ID: str | None = None

# ─── Death tracking ──────────────────────────────────────────────────────── #
death_buffer: collections.deque = collections.deque(maxlen=500)
last_alive: dict[str, bool] = {}


# ═══════════════════════════════════════════════════════════════════════════ #
#   HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════ #

def now_ts() -> int:
    return int(time.time())


def team_of(p: dict) -> int:
    """Return team number: 2 = Radiant, 3 = Dire."""
    return p.get("team2") or p.get("team") or 0


def gold_adv(gsi: dict) -> int:
    """Compute Radiant gold advantage."""
    m = gsi.get("map", {})
    if "radiant_gold_adv" in m:
        return m["radiant_gold_adv"]
    adv = 0
    for p in gsi.get("allplayers", {}).values():
        sign = 1 if team_of(p) == 2 else -1
        adv += p.get("net_worth", p.get("gold", 0)) * sign
    return adv


def xp_adv(gsi: dict) -> int:
    """Compute Radiant XP advantage."""
    return gsi.get("map", {}).get("radiant_xp_adv", 0)


def core_ids(gsi: dict, n: int = 2) -> dict[str, list[str]]:
    """Top-N richest Steam IDs per team."""
    rad: list[tuple[int, str]] = []
    dire: list[tuple[int, str]] = []
    for sid, p in gsi.get("allplayers", {}).items():
        nw = p.get("net_worth", p.get("gold", 0))
        (rad if team_of(p) == 2 else dire).append((nw, sid))
    return {
        "R": [s for _, s in sorted(rad,  reverse=True)[:n]],
        "D": [s for _, s in sorted(dire, reverse=True)[:n]],
    }


def update_deaths(gsi: dict) -> None:
    """Track new deaths by diffing alive status."""
    ts = now_ts()
    for sid, p in gsi.get("allplayers", {}).items():
        alive_now = p.get("alive", True)
        was_alive = last_alive.get(sid, True)
        if was_alive and not alive_now:
            death_buffer.append(ts)
        last_alive[sid] = alive_now


def recent_deaths_count(window: int = 15) -> int:
    cutoff = now_ts() - window
    return sum(1 for d in death_buffer if d >= cutoff)


def enemy_t3_down(gsi: dict, my_team: int) -> int:
    """
    Check if any enemy T3 tower is destroyed.
    Adapts to player perspective (Radiant/Dire).
    """
    enemy_side = "dire" if my_team == 2 else "radiant"
    buildings = gsi.get("buildings", {}).get(enemy_side, {})
    t3_keys = [k for k in buildings if "tower3" in k]
    if not t3_keys:
        return 0
    return int(any(buildings[k].get("health", 1) == 0 for k in t3_keys))


def roshan_alive(gsi: dict) -> int:
    state = gsi.get("map", {}).get("roshan_state", "")
    return 1 if state == "alive" else 0


def reset_match_state() -> None:
    """Reset transient state for a new match."""
    global HINT, HINT_ACTION, HINT_CONFIDENCE, LAST_FEATURES
    death_buffer.clear()
    last_alive.clear()
    HINT = "New match detected…"
    HINT_ACTION = ""
    HINT_CONFIDENCE = 0.0
    LAST_FEATURES = {}
    print("[runtime] State reset for new match")


# ═══════════════════════════════════════════════════════════════════════════ #
#   FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════ #

def compute_features(gsi: dict, my_team: int) -> dict:
    """
    Extract 12 features from a live GSI snapshot.
    Perspective-aware: gold/xp are inverted if player is Dire,
    so the model always sees "our team advantage" in the same sign direction.
    """
    sign = 1 if my_team == 2 else -1
    g = gold_adv(gsi) * sign
    x = xp_adv(gsi) * sign

    our_alive_n = enemy_alive_n = our_dead_n = enemy_dead_n = 0
    for p in gsi.get("allplayers", {}).values():
        alive = p.get("alive", True)
        if team_of(p) == my_team:
            our_alive_n += alive
            our_dead_n  += (not alive)
        else:
            enemy_alive_n += alive
            enemy_dead_n  += (not alive)

    cores = core_ids(gsi)
    our_key   = "R" if my_team == 2 else "D"
    enemy_key = "D" if my_team == 2 else "R"
    our_core_alive_n   = sum(last_alive.get(s, True)  for s in cores[our_key])
    enemy_core_alive_n = sum(last_alive.get(s, True)  for s in cores[enemy_key])
    enemy_core_dead_n  = max(0, 2 - enemy_core_alive_n)

    return {
        "gold_adv":             g,
        "xp_adv":               x,
        "our_dead_tot":         our_dead_n,
        "enemy_dead_tot":       enemy_dead_n,
        "our_alive":            our_alive_n,
        "enemy_alive":          enemy_alive_n,
        "our_core_alive":       our_core_alive_n,
        "enemy_core_alive":     enemy_core_alive_n,
        "enemy_core_dead":      enemy_core_dead_n,
        "roshan_alive":         roshan_alive(gsi),
        "recent_deaths":        recent_deaths_count(15),
        "towers_dire_t3_down":  enemy_t3_down(gsi, my_team),
    }


# ═══════════════════════════════════════════════════════════════════════════ #
#   ROUTES
# ═══════════════════════════════════════════════════════════════════════════ #

@app.route("/gsi", methods=["POST"])
def handle_gsi():
    global STATE, LAST_GSI_TS, GSI_COUNT, CURRENT_MATCH_ID

    if not request.is_json:
        abort(400, "Need JSON")
    payload = request.get_json(force=True)

    # Log to disk
    ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    (LOG_DIR / f"{ts_str}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    # Detect match change → reset state
    new_match_id = payload.get("map", {}).get("matchid")
    if new_match_id and new_match_id != CURRENT_MATCH_ID:
        reset_match_state()
        CURRENT_MATCH_ID = new_match_id

    with LOCK:
        STATE.clear()
        STATE.update(payload)
        LAST_GSI_TS = now_ts()
        GSI_COUNT += 1

    update_deaths(payload)
    return "OK", 200


@app.route("/hint")
def get_hint():
    stale = (now_ts() - LAST_GSI_TS) > 5 if LAST_GSI_TS else True
    return jsonify({
        "hint":         HINT,
        "action":       HINT_ACTION,
        "confidence":   round(HINT_CONFIDENCE, 3),
        "last_gsi_ts":  LAST_GSI_TS,
        "stale":        stale,
    })


@app.route("/health")
def health():
    model_status = "unknown"
    try:
        r = http_requests.get(f"{MODEL_API_URL}/health", timeout=1)
        model_status = "reachable" if r.status_code == 200 else f"error ({r.status_code})"
    except Exception:
        model_status = "unreachable"

    return jsonify({
        "status":               "ok",
        "model_api":            model_status,
        "last_gsi_ts":          LAST_GSI_TS,
        "gsi_packets_received": GSI_COUNT,
        "current_match_id":     CURRENT_MATCH_ID,
    })


@app.route("/debug/state")
def debug_state():
    with LOCK:
        return jsonify(STATE.copy())


@app.route("/debug/features")
def debug_features():
    return jsonify(LAST_FEATURES.copy())


# ═══════════════════════════════════════════════════════════════════════════ #
#   PREDICTION LOOP (background thread)
# ═══════════════════════════════════════════════════════════════════════════ #

def prediction_loop():
    """Continually compute features and query the model whenever new GSI data arrives."""
    global HINT, HINT_ACTION, HINT_CONFIDENCE, LAST_FEATURES

    my_team: int | None = None
    last_processed_ts = 0

    while True:
        time.sleep(0.4)

        with LOCK:
            if not STATE:
                continue
            if LAST_GSI_TS <= last_processed_ts:
                continue  # no new data
            gsi = STATE.copy()
            last_processed_ts = LAST_GSI_TS

        # Determine player's team (re-read each time for reconnect safety)
        pt = gsi.get("player", {}).get("team2") or gsi.get("player", {}).get("team")
        if pt is not None:
            my_team = pt
        if my_team is None:
            my_team = 2  # default Radiant

        vec = compute_features(gsi, my_team)
        LAST_FEATURES = vec.copy()

        # Query model API
        try:
            r = http_requests.post(
                f"{MODEL_API_URL}/predict", json=vec, timeout=0.5
            )
            data = r.json()
            action     = data.get("action", "")
            confidence = data.get("confidence", 0.0)

            HINT_ACTION     = action
            HINT_CONFIDENCE = confidence
            HINT            = LABEL2TXT.get(action, f"❓ {action}")

        except Exception:
            # Keep last valid hint — don't silently replace with FARM
            if not HINT_ACTION:
                HINT = "⚠️ Model offline"


# ═══════════════════════════════════════════════════════════════════════════ #
#   MAIN
# ═══════════════════════════════════════════════════════════════════════════ #

def main():
    parser = argparse.ArgumentParser(description="Aegis Assistant — live runtime server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--capture-minimap", action="store_true",
                        help="Enable experimental minimap capture (Windows-only)")
    args = parser.parse_args()

    # Optional minimap capture
    if args.capture_minimap:
        try:
            import screenshot
            screenshot.start()
            print("✓ Minimap capture started (experimental)")
        except ImportError:
            print("⚠ screenshot module unavailable — install opencv-python + mss")
        except Exception as exc:
            print(f"⚠ Minimap capture error: {exc}")

    # Start background prediction loop
    threading.Thread(target=prediction_loop, daemon=True).start()
    print(f"✓ Runtime server on http://{args.host}:{args.port}")
    print(f"  Model API: {MODEL_API_URL}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
