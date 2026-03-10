#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dataset.py — "logic-v3" with leakage fixes.

Generates a snapshot CSV from raw OpenDota match JSONs.
Each row = one moment in a match with 12 features + a heuristic macro-label.

Macro-labels (9):
  FARM            — default: safe farming phase
  STACK           — everyone alive, game is even (|gold_adv| <= 2k)
  GANK            — we have 3+ alive, one enemy core isolated
  PUSH            — gold_adv > 4k, few enemies dead
  DEFEND          — gold_adv < -4k, few allies dead
  TEAMFIGHT       — >= 6 deaths in the last 15 seconds
  TAKE_ROSHAN     — Roshan alive, 3+ enemy cores dead, our cores alive
  CONTEST_ROSHAN  — Roshan alive, both teams have cores, recent skirmish
  SIEGE           — gold_adv > 10k, at least one enemy T3 tower destroyed

Leakage fixes vs. original version:
  1. recent_deaths: only looks backward (t-15..t), not forward
  2. Core identification: uses gold_t[t_idx] instead of end-of-match total_gold
  3. Player identity: uses player_slot (always present) instead of account_id
  4. Tower status: reconstructed from objectives timeline, not final bitmask
  5. Roshan respawn: documented as approximation (fixed 480s window)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pandas as pd


# ─── Time-series helpers ──────────────────────────────────────────────────── #

def _sum_series(players: list[dict], key: str, length: int) -> list[int]:
    """Sum a per-minute time series across players."""
    arr = [0] * length
    for p in players:
        series = p.get(key, [])
        for i, v in enumerate(series[:length]):
            arr[i] += v
    return arr


def gold_xp_adv(match: dict) -> tuple[list[int], list[int]]:
    """Compute per-minute Radiant gold/XP advantage."""
    radiant = [p for p in match["players"] if p.get("isRadiant")]
    dire    = [p for p in match["players"] if not p.get("isRadiant")]
    length  = max(
        max((len(p.get("gold_t", [])) for p in match["players"]), default=1), 1
    )
    g_r, g_d = _sum_series(radiant, "gold_t", length), _sum_series(dire, "gold_t", length)
    x_r, x_d = _sum_series(radiant, "xp_t",   length), _sum_series(dire, "xp_t",   length)
    g_adv = [r - d for r, d in zip(g_r, g_d)]
    x_adv = [r - d for r, d in zip(x_r, x_d)]
    return g_adv, x_adv


# ─── Death tracking (no future leakage) ──────────────────────────────────── #

def deaths_map(match: dict) -> dict[int, list[int]]:
    """Map player_slot → sorted list of death times."""
    return {
        p["player_slot"]: sorted(p.get("death_times", []))
        for p in match["players"]
    }


def is_dead(slot: int, t: int, table: dict[int, list[int]], respawn: int = 40) -> bool:
    """Check if a player is dead at time t (died within [t-respawn, t])."""
    return any(d <= t < d + respawn for d in table.get(slot, []))


def count_recent_deaths(table: dict[int, list[int]], t: int, window: int = 15) -> int:
    """Count deaths in [t-window, t] — only past, no future leakage."""
    return sum(
        1 for times in table.values()
        for d in times
        if t - window <= d <= t
    )


# ─── Core identification by snapshot gold (not end-of-match) ─────────────── #

def richest_at(match: dict, t_idx: int, n: int = 2) -> dict[str, list[int]]:
    """
    Identify top-N richest players per team at minute t_idx.
    Uses gold_t[t_idx] instead of total_gold to avoid future leakage.
    """
    def get_gold(p: dict, idx: int) -> int:
        gt = p.get("gold_t", [])
        if not gt:
            return 0
        return gt[min(idx, len(gt) - 1)]

    radiant = [p for p in match["players"] if p.get("isRadiant")]
    dire    = [p for p in match["players"] if not p.get("isRadiant")]

    rad_sorted  = sorted(radiant, key=lambda p: get_gold(p, t_idx), reverse=True)
    dire_sorted = sorted(dire,    key=lambda p: get_gold(p, t_idx), reverse=True)

    return {
        "R": [p["player_slot"] for p in rad_sorted[:n]],
        "D": [p["player_slot"] for p in dire_sorted[:n]],
    }


# ─── Tower reconstruction from objectives ────────────────────────────────── #

def t3_dire_kill_times(match: dict) -> list[int]:
    """
    Extract times when Dire T3 towers were destroyed, from the objectives array.
    If objectives data is missing/incomplete, returns empty list (→ feature = 0).
    """
    times = []
    for obj in match.get("objectives", []):
        key = str(obj.get("key", ""))
        if "badguys" in key and "tower3" in key:
            t = obj.get("time")
            if t is not None:
                times.append(t)
    return sorted(times)


# ─── Roshan tracking (approximation, documented) ─────────────────────────── #

def roshan_kill_times(match: dict) -> list[int]:
    """Extract Roshan kill times from objectives."""
    return sorted(
        e["time"]
        for e in match.get("objectives", [])
        if e.get("type") == "CHAT_MESSAGE_ROSHAN_KILL" and "time" in e
    )


def is_roshan_alive(t: int, rosh_kills: list[int], respawn_approx: int = 480) -> int:
    """
    Approximate Roshan alive status.
    NOTE: Real Roshan respawn is 8-11 min (random). We use 8 min (480s)
    as a conservative lower bound. This is documented as an approximation.
    """
    for kill_time in rosh_kills:
        if kill_time <= t < kill_time + respawn_approx:
            return 0
    return 1


# ─── Label rules ──────────────────────────────────────────────────────────── #

def label(row: dict) -> str:
    """Assign a heuristic macro-action label based on game state features."""
    if row["recent_deaths"] >= 6:
        return "TEAMFIGHT"

    if row["roshan_alive"]:
        if row["enemy_core_dead"] >= 1 and row["our_core_alive"] >= 2:
            return "TAKE_ROSHAN"
        if (row["our_core_alive"] >= 2
                and row["enemy_core_alive"] >= 2
                and row["recent_deaths"] >= 2):
            return "CONTEST_ROSHAN"

    if row["gold_adv"] > 10_000 and row["towers_dire_t3_down"]:
        return "SIEGE"

    if row["gold_adv"] > 4_000 and row["enemy_dead_tot"] <= 1:
        return "PUSH"

    if row["gold_adv"] < -4_000 and row["our_dead_tot"] <= 1:
        return "DEFEND"

    if (row["our_alive"] >= 3
            and row["enemy_core_alive"] == 1
            and row["recent_deaths"] < 2):
        return "GANK"

    if (row["our_dead_tot"] == 0
            and row["enemy_dead_tot"] == 0
            and abs(row["gold_adv"]) <= 2_000):
        return "STACK"

    return "FARM"


# ─── Snapshot generation ──────────────────────────────────────────────────── #

def snapshots(match: dict, step: int) -> list[dict]:
    """Generate labeled feature rows every `step` seconds for one match."""
    dur = match.get("duration", 0)
    if dur <= 0:
        return []

    g_adv, x_adv = gold_xp_adv(match)
    deaths  = deaths_map(match)
    rosh    = roshan_kill_times(match)
    t3_kill = t3_dire_kill_times(match)

    rows: list[dict] = []
    for t in range(0, dur, step):
        idx = min(t // 60, len(g_adv) - 1)
        ga, xa = g_adv[idx], x_adv[idx]

        # Determine cores at this moment (not end-of-match)
        cores = richest_at(match, idx, n=2)

        # Count alive/dead per team
        our_alive = enemy_alive = our_dead = enemy_dead = 0
        our_core_dead = enemy_core_dead = 0

        for p in match["players"]:
            slot = p["player_slot"]
            dead = is_dead(slot, t, deaths, respawn=40)

            if p.get("isRadiant"):
                our_dead  += dead
                our_alive += (not dead)
                if slot in cores["R"]:
                    our_core_dead += dead
            else:
                enemy_dead  += dead
                enemy_alive += (not dead)
                if slot in cores["D"]:
                    enemy_core_dead += dead

        # Towers: reconstructed from objectives (honest)
        towers_down = int(any(et <= t for et in t3_kill))

        row = dict(
            match_id=match["match_id"],
            t=t,
            gold_adv=ga,
            xp_adv=xa,
            our_alive=our_alive,
            enemy_alive=enemy_alive,
            our_dead_tot=our_dead,
            enemy_dead_tot=enemy_dead,
            our_core_alive=2 - our_core_dead,
            enemy_core_alive=2 - enemy_core_dead,
            enemy_core_dead=enemy_core_dead,
            roshan_alive=is_roshan_alive(t, rosh),
            recent_deaths=count_recent_deaths(deaths, t, window=15),
            towers_dire_t3_down=towers_down,
        )
        row["label"] = label(row)
        rows.append(row)

    return rows


# ─── Build pipeline ──────────────────────────────────────────────────────── #

def build(raw: pathlib.Path, out: pathlib.Path, step: int) -> None:
    rows: list[dict] = []
    skipped = 0

    json_files = list(raw.glob("*.json"))
    if not json_files:
        print(f"⚠ No JSON files found in {raw}", file=sys.stderr)
        sys.exit(1)

    for i, fp in enumerate(json_files, 1):
        try:
            match = json.loads(fp.read_text(encoding="utf-8"))
            rows.extend(snapshots(match, step))
            if i % 100 == 0:
                print(f"  processed {i}/{len(json_files)} files…")
        except Exception as exc:
            skipped += 1
            print(f"  SKIP {fp.name}: {exc}", file=sys.stderr)

    if not rows:
        print("⚠ No rows generated — check your data/raw directory", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)

    print(f"\n{'─' * 50}")
    print(f"LABEL BALANCE:\n{df['label'].value_counts().to_string()}")
    print(f"{'─' * 50}")
    print(f"✓ Dataset saved → {out}")
    print(f"  Rows: {len(df):,}  |  Matches: {df['match_id'].nunique():,}  |  Skipped: {skipped}")


def main():
    ap = argparse.ArgumentParser(description="Build snapshot dataset from raw match JSONs")
    ap.add_argument("--raw",  type=pathlib.Path, default=pathlib.Path("data/raw"))
    ap.add_argument("--out",  type=pathlib.Path, default=pathlib.Path("data/snapshots/dataset_v3.csv"))
    ap.add_argument("--step", type=int, default=5, help="Snapshot interval in seconds")
    args = ap.parse_args()

    build(args.raw, args.out, args.step)


if __name__ == "__main__":
    main()
