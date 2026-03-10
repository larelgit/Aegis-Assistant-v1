#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
replay_gsi.py — replay saved GSI packets or generate synthetic demo data.

Sends JSON packets to the runtime server's /gsi endpoint, simulating a live game.
Essential for demonstrating the project without Dota 2.

Usage:
    # Replay saved logs:
    python scripts/replay_gsi.py demo/gsi/

    # Generate and replay synthetic demo:
    python scripts/replay_gsi.py --generate

    # Generate and save to disk only:
    python scripts/replay_gsi.py --generate --save-to demo/gsi/
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time

import requests

DEFAULT_TARGET = "http://127.0.0.1:5000/gsi"


# ─── Synthetic demo packet generator ─────────────────────────────────────── #

def generate_demo_packets(count: int = 20, seed: int = 42) -> list[dict]:
    """
    Generate synthetic GSI-like packets simulating phases of a ~40 min Dota 2 game.
    Phases: early farm → gank → small fight → push → roshan → teamfight → siege.
    """
    rng = random.Random(seed)
    packets = []
    match_id = "demo_7654321"

    # Game timeline: each packet = ~2 min apart
    for i in range(count):
        clock = 60 + i * 120  # seconds
        phase = i / count      # 0..1

        # Simulate gold advantage progression
        base_gold_adv = int(1000 * (phase - 0.3) * 15 + rng.randint(-500, 500))

        # Player states
        players = {}
        for j in range(10):
            team = 2 if j < 5 else 3
            nw = 2000 + int(phase * 15000) + j * 400 + rng.randint(-300, 300)

            # Simulate deaths based on game phase
            alive = True
            if 0.3 <= phase <= 0.5:      # mid-game skirmishes
                alive = rng.random() > 0.12
            elif 0.6 <= phase <= 0.75:    # teamfight phase
                alive = rng.random() > 0.25
            elif phase > 0.85:            # late push / siege
                # Enemy (Dire) dying more
                if team == 3:
                    alive = rng.random() > 0.35
                else:
                    alive = rng.random() > 0.08

            players[f"player_{j}"] = {
                "team": team,
                "net_worth": max(0, nw),
                "gold": max(0, nw // 5),
                "alive": alive,
            }

        # Roshan state
        roshan_state = "alive"
        if 0.55 <= phase <= 0.65:
            roshan_state = "dead"

        # Tower status
        t3_health = 1800 if phase < 0.8 else 0

        packet = {
            "map": {
                "matchid": match_id,
                "clock_time": clock,
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "roshan_state": roshan_state,
            },
            "player": {"team2": 2},
            "allplayers": players,
            "buildings": {
                "dire": {
                    f"dota_badguys_tower3_{pos}": {
                        "health": t3_health,
                        "max_health": 1800,
                    }
                    for pos in ["top", "mid", "bot"]
                },
            },
        }
        packets.append(packet)

    return packets


# ─── Replay logic ─────────────────────────────────────────────────────────── #

def load_packets(directory: pathlib.Path) -> list[dict]:
    """Load and sort GSI JSON files from a directory."""
    files = sorted(directory.glob("*.json"))
    if not files:
        print(f"✗ No JSON files in {directory}", file=sys.stderr)
        sys.exit(1)

    packets = []
    for f in files:
        try:
            packets.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"  SKIP {f.name}: {exc}", file=sys.stderr)
    return packets


def replay(packets: list[dict], target: str, delay: float) -> None:
    """Send packets to GSI endpoint with delay between each."""
    print(f"Replaying {len(packets)} packets to {target} (delay={delay}s)")
    print("─" * 50)

    for i, pkt in enumerate(packets, 1):
        clock = pkt.get("map", {}).get("clock_time", "?")
        try:
            r = requests.post(target, json=pkt, timeout=2)
            status = r.status_code
        except Exception as exc:
            status = f"ERR: {exc}"

        print(f"  [{i}/{len(packets)}] clock={clock}  → {status}")
        time.sleep(delay)

    print("─" * 50)
    print("✓ Replay complete")


def main():
    ap = argparse.ArgumentParser(description="Replay GSI packets or generate demo data")
    ap.add_argument("directory", nargs="?", type=pathlib.Path,
                    help="Directory with saved GSI JSON files")
    ap.add_argument("--generate", action="store_true",
                    help="Generate synthetic demo packets instead of loading from disk")
    ap.add_argument("--save-to", type=pathlib.Path, default=None,
                    help="Save generated packets to this directory (and exit)")
    ap.add_argument("--target", default=DEFAULT_TARGET,
                    help=f"GSI endpoint URL (default: {DEFAULT_TARGET})")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="Seconds between packets (default: 1.5)")
    ap.add_argument("--count", type=int, default=20,
                    help="Number of demo packets to generate (default: 20)")
    args = ap.parse_args()

    if args.generate:
        packets = generate_demo_packets(args.count)

        if args.save_to:
            args.save_to.mkdir(parents=True, exist_ok=True)
            for i, pkt in enumerate(packets):
                fp = args.save_to / f"demo_{i:04d}.json"
                fp.write_text(json.dumps(pkt, indent=2), encoding="utf-8")
            print(f"✓ Saved {len(packets)} demo packets to {args.save_to}/")
            return

        replay(packets, args.target, args.delay)

    elif args.directory:
        packets = load_packets(args.directory)
        replay(packets, args.target, args.delay)

    else:
        ap.print_help()
        print("\nExamples:")
        print("  python scripts/replay_gsi.py --generate")
        print("  python scripts/replay_gsi.py demo/gsi/")


if __name__ == "__main__":
    main()
