#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aegis Assistant — MVP 2
• принимает GSI (/gsi)
• считает 12 фич для LightGBM v3
• запрашивает /predict → отдаёт подсказку браузерному оверлею (/hint)
"""

from __future__ import annotations
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from datetime import datetime, UTC
from pathlib import Path
import json, threading, time, requests, collections

import screenshot      # ваш модуль «делаем скриншот миникарты»

# ---------------------------------------------------------------------------#
app = Flask(__name__)
CORS(app)
LOG = Path("gsi_logs"); LOG.mkdir(exist_ok=True)

STATE: dict = {}           # последняя GSI‑снимка
HINT  = "..."              # текст в оверлее
LOCK  = threading.Lock()

# --- постоянные -------------------------------------------------------------#
FEATURES = [
    "gold_adv", "xp_adv",
    "our_dead_tot", "enemy_dead_tot",
    "our_alive", "enemy_alive",
    "our_core_alive", "enemy_core_alive", "enemy_core_dead",
    "roshan_alive", "recent_deaths", "towers_dire_t3_down",
]

LABEL2TXT = {
    "FARM":   "💰 Фарм",
    "STACK":  "📦 Стак",
    "PUSH":   "⚔️ Давим",
    "DEFEND": "🛡️ Деф",
    "SIEGE":  "🏰 Штурм",
}

# --- вспомогалки ------------------------------------------------------------#
death_buffer = collections.deque(maxlen=200)   # (timestamp)
last_alive   = {}                              # steamid -> bool

def now_ts() -> int: return int(time.time())

def team_of_player(p: dict) -> int:
    # team: 2 – Radiant, 3 – Dire (по GSI)
    return p.get("team") or p.get("team2") or 0

def gold_adv(gsi: dict) -> int:
    # попробуем взять готовое поле, иначе считаем “на коленке”
    map_blk = gsi.get("map", {})
    if "radiant_gold_adv" in map_blk:
        return map_blk["radiant_gold_adv"]
    adv = 0
    for p in gsi.get("allplayers", {}).values():
        side = 1 if team_of_player(p) == 2 else -1
        adv += p.get("net_worth", p.get("gold", 0)) * side
    return adv

def xp_adv(gsi: dict) -> int:
    return gsi.get("map", {}).get("radiant_xp_adv", 0)

def core_ids(gsi: dict, n=2):
    rad, dire = [], []
    for sid, p in gsi.get("allplayers", {}).items():
        t = team_of_player(p)
        nw = p.get("net_worth", p.get("gold", 0))
        (rad if t == 2 else dire).append((nw, sid))
    rad_ids  = [sid for _, sid in sorted(rad,  reverse=True)[:n]]
    dire_ids = [sid for _, sid in sorted(dire, reverse=True)[:n]]
    return {"R": rad_ids, "D": dire_ids}

def update_deaths(gsi: dict):
    ts = now_ts()
    for sid, p in gsi.get("allplayers", {}).items():
        alive = p.get("alive", True)
        was   = last_alive.get(sid, True)
        if was and not alive:
            death_buffer.append(ts)
        last_alive[sid] = alive

def recent_deaths_window(sec=15) -> int:
    cut = now_ts() - sec
    return sum(1 for d in death_buffer if d >= cut)

def towers_dire_t3_down(gsi: dict):
    # buildings[].name содержит 'dota_badguys_tower3_*'
    blds = gsi.get("map", {}).get("buildings", [])
    t3   = [b for b in blds if "_tower3_" in b.get("name","")]
    return int(all(b.get("health",1) == 0 for b in t3)) if t3 else 0

def roshan_alive(gsi: dict):
    rs = gsi.get("map", {}).get("roshan_state", "")
    return 1 if rs == "alive" else 0

# ---------------------------------------------------------------------------#
@app.route("/gsi", methods=["POST"])
def handle_gsi():
    if not request.is_json: abort(400, "Need JSON")
    payload = request.get_json(force=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    (LOG / f"{ts}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with LOCK:
        STATE.clear(); STATE.update(payload)
    update_deaths(payload)
    return "OK", 200

@app.route("/hint")
def get_hint(): return jsonify({"hint": HINT, "ts": now_ts()})

# ---------------------------------------------------------------------------#
def rule_engine():
    global HINT
    my_team = None           # определим один раз

    while True:
        time.sleep(0.5)
        with LOCK:
            if not STATE: continue
            gsi = STATE.copy()

        if my_team is None:
            my_team = gsi.get("player", {}).get("team", 2)  # 2 / 3

        # --- вычисляем признаки ------------------------------------------
        gold     = gold_adv(gsi)
        xp       = xp_adv(gsi)

        our_alive = enemy_alive = our_dead = enemy_dead = 0
        for p in gsi.get("allplayers", {}).values():
            alive = p.get("alive", True)
            if team_of_player(p) == my_team:
                our_alive  += alive
                our_dead   += (not alive)
            else:
                enemy_alive  += alive
                enemy_dead   += (not alive)

        cores = core_ids(gsi)
        our_core_alive    = sum(last_alive.get(sid, True) for sid in cores["R" if my_team==2 else "D"])
        enemy_core_alive  = sum(last_alive.get(sid, True) for sid in cores["D" if my_team==2 else "R"])
        enemy_core_dead   = 2 - enemy_core_alive

        vec = dict(
            gold_adv=gold, xp_adv=xp,
            our_dead_tot=our_dead, enemy_dead_tot=enemy_dead,
            our_alive=our_alive, enemy_alive=enemy_alive,
            our_core_alive=our_core_alive,
            enemy_core_alive=enemy_core_alive,
            enemy_core_dead=enemy_core_dead,
            roshan_alive=roshan_alive(gsi),
            recent_deaths=recent_deaths_window(15),
            towers_dire_t3_down=towers_dire_t3_down(gsi),
        )

        # --- запрос модели -----------------------------------------------
        try:
            r = requests.post("http://127.0.0.1:8000/predict", json=vec, timeout=0.3)
            label = r.json().get("action", "FARM")
        except Exception:
            label = "FARM"

        HINT = LABEL2TXT.get(label, "🤔")

# ---------------------------------------------------------------------------#
if __name__ == "__main__":
    screenshot.start()                                 # поток скриншота
    threading.Thread(target=rule_engine, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
