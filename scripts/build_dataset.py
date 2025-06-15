#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dataset.py  • “logic‑v3”

Макро‑метки (9):
• FARM            – спокойный фарм
• STACK           – вся команда фармит (ни одного героя на карте нет мёртвым),
                    а gold_adv ∈ (-2k … +2k)
• GANK            – ↘ мы ≥3 живы, враг‑core 1 жив, ≤2 враги рядом с ним мертвы
• PUSH            – gold_adv > +4k, врагов мёртвых ≤1
• DEFEND          – gold_adv < –4k, наши мёртвые ≤1
• TEAMFIGHT       – смертей ≥6 за 15 с
• TAKE_ROSHAN     – Рошан жив, врагов мёртвых ≥3, у нас ≥2 core живы
• CONTEST_ROSHAN  – Рошан жив, обе команды ≥2 core живы, смертей ≥2 за 15 с
• SIEGE           – gold_adv > +10k и у Dire разрушено ≥1 T3 башен
"""

from __future__ import annotations
import argparse, json, pathlib, sys
import pandas as pd

# ---------------------------------------------------------------------------#
def series(players, key, length, default=0):
    arr = [0]*length
    for p in players:
        if key in p and p[key]:
            for i, v in enumerate(p[key][:length]):
                arr[i] += v
    return arr

def gold_xp_adv(match):
    R = [p for p in match["players"] if p["isRadiant"]]
    D = [p for p in match["players"] if not p["isRadiant"]]
    length = max(max(len(p.get("gold_t",[])) for p in match["players"]), 1)
    g_adv = [r-d for r,d in zip(series(R,"gold_t",length), series(D,"gold_t",length))]
    x_adv = [r-d for r,d in zip(series(R,"xp_t",  length), series(D,"xp_t",  length))]
    return g_adv, x_adv

def deaths_map(match):   # {id: [times]}
    return {p["account_id"]: p.get("death_times",[]) for p in match["players"]}

def richest_ids(match, n=2):
    f = lambda lst: [p["account_id"] for p in
                     sorted(lst, key=lambda p: p.get("total_gold",0), reverse=True)[:n]]
    return {
        "R": f([p for p in match["players"] if p["isRadiant"]]),
        "D": f([p for p in match["players"] if not p["isRadiant"]])
    }

def is_dead(pid, t, table, resp=40):
    return any(d <= t < d+resp for d in table.get(pid, []))

# -------------- Label rules -------------------------------------------------#
def label(row):
    if row["recent_deaths"] >= 6:
        return "TEAMFIGHT"

    if row["roshan_alive"]:
        if row["enemy_core_dead"] >= 1 and row["our_core_alive"] >= 2:
            return "TAKE_ROSHAN"
        if row["our_core_alive"] >= 2 and row["enemy_core_alive"] >= 2 and row["recent_deaths"] >= 2:
            return "CONTEST_ROSHAN"

    if row["gold_adv"] > 10000 and row["towers_dire_t3_down"]:
        return "SIEGE"

    if row["gold_adv"] > 4000 and row["enemy_dead_tot"] <= 1:
        return "PUSH"

    if row["gold_adv"] < -4000 and row["our_dead_tot"] <= 1:
        return "DEFEND"

    # GANK – у нас минимум 3 живых, у врага core‑solo, и недавних смертей <2
    if (row["our_alive"] >= 3 and row["enemy_core_alive"] == 1
        and row["recent_deaths"] < 2):
        return "GANK"

    # STACK – nobody dead, игра ровная
    if row["our_dead_tot"] == 0 and row["enemy_dead_tot"] == 0 \
       and abs(row["gold_adv"]) <= 2000:
        return "STACK"

    return "FARM"

# ---------------------------------------------------------------------------#
def snapshots(match, step):
    dur = match["duration"]
    g_adv, x_adv = gold_xp_adv(match)
    deaths = deaths_map(match)
    cores  = richest_ids(match, 2)
    rosh = [e["time"] for e in match.get("objectives",[])
            if e.get("type")=="CHAT_MESSAGE_ROSHAN_KILL"]

    rows=[]
    for t in range(0,dur,step):
        idx = min(t//60, len(g_adv)-1)
        ga, xa = g_adv[idx], x_adv[idx]

        our_alive=enemy_alive=our_dead=enemy_dead=0
        our_core_dead=enemy_core_dead=0
        for p in match["players"]:
            dead = is_dead(p["account_id"], t, deaths, p.get("respawn_time",40))
            if p["isRadiant"]:
                our_dead += dead; our_alive += (not dead)
                if p["account_id"] in cores["R"]: our_core_dead += dead
            else:
                enemy_dead += dead; enemy_alive += (not dead)
                if p["account_id"] in cores["D"]: enemy_core_dead += dead

        roshan_alive=1
        for kill in rosh:
            if kill<=t<kill+600: roshan_alive=0

        recent = sum(1 for arr in deaths.values() for d in arr if t-7<=d<=t+7)

        t3_mask = 0b111000   #  bits 3‑5 (T3)
        towers_down = (match.get("tower_status_dire",0)&t3_mask)==0

        row=dict(
            match_id=match["match_id"], t=t,
            gold_adv=ga, xp_adv=xa,
            our_alive=our_alive, enemy_alive=enemy_alive,
            our_dead_tot=our_dead, enemy_dead_tot=enemy_dead,
            our_core_alive=2-our_core_dead,
            enemy_core_alive=2-enemy_core_dead,
            enemy_core_dead=enemy_core_dead,
            roshan_alive=roshan_alive,
            recent_deaths=recent,
            towers_dire_t3_down=int(towers_down),
        )
        row["label"]=label(row)
        rows.append(row)
    return rows

# ---------------------------------------------------------------------------#
def build(raw: pathlib.Path, out: pathlib.Path, step:int):
    rows, skipped= [],0
    for fp in raw.glob("*.json"):
        try:
            rows.extend(snapshots(json.loads(fp.read_text()), step))
        except Exception as e:
            skipped+=1; print("skip",fp.name,e,file=sys.stderr)

    if not rows:
        print("⚠ no rows – проверьте data/raw"); sys.exit(1)

    df=pd.DataFrame(rows)
    print("LABEL BALANCE:\n",df["label"].value_counts())
    df.to_csv(out,index=False)
    print(f"✓ dataset saved → {out} | rows: {len(df):,}  skipped: {skipped}")

# ---------------------------------------------------------------------------#
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--raw",type=pathlib.Path,default=pathlib.Path("data/raw"))
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("data/snapshots/dataset_v3.csv"))
    p.add_argument("--step",type=int,default=5)
    a=p.parse_args(); a.out.parent.mkdir(parents=True,exist_ok=True)
    build(a.raw,a.out,a.step)
