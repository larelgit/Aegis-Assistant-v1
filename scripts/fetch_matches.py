#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_matches.py — download high-MMR matches from OpenDota.

Usage:
    python scripts/fetch_matches.py --count 1000 --min-rank 70

Environment:
    OD_API_KEY — OpenDota API key (optional, increases rate limit).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys
import time

import requests

OD_API = "https://api.opendota.com/api"


def create_session(api_key: str | None = None) -> requests.Session:
    """Create a requests Session with default params and headers."""
    s = requests.Session()
    s.headers["User-Agent"] = "AegisAssistant/1.0 (github.com/larelgit/Aegis-Assistant-v1)"
    if api_key:
        s.params["api_key"] = api_key  # type: ignore[assignment]
    return s


def GET(session: requests.Session, endpoint: str,
        params: dict | None = None, retries: int = 5):
    """GET with exponential backoff on 429 / 5xx."""
    params = params or {}
    backoff = 2.0
    for attempt in range(1, retries + 1):
        r = session.get(f"{OD_API}/{endpoint.lstrip('/')}", params=params, timeout=20)
        if r.status_code == 429:
            delay = backoff + random.random()
            print(f"  [429] retry {attempt}/{retries} in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
            backoff *= 2
            continue
        try:
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as exc:
            if attempt == retries or r.status_code < 500:
                raise exc
            delay = backoff + random.random()
            print(f"  [{r.status_code}] retry in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
            backoff *= 2
    return None


def collect_ids(session: requests.Session, n: int, min_rank: int) -> list[int]:
    """Page through publicMatches and collect match IDs above min_rank."""
    ids: list[int] = []
    seen: set[int] = set()
    last: int | None = None
    has_key = bool(session.params.get("api_key"))

    while len(ids) < n:
        params = {"less_than_match_id": last} if last else {}
        batch = GET(session, "publicMatches", params)
        if not batch:
            break
        for m in batch:
            mid = m["match_id"]
            last = mid
            if mid in seen:
                continue
            seen.add(mid)
            if m.get("avg_rank_tier", 0) >= min_rank:
                ids.append(mid)
                if len(ids) >= n:
                    break
        time.sleep(0.5 if has_key else 1.1)
    return ids


def save_match(session: requests.Session, mid: int, out: pathlib.Path) -> bool:
    """Download and save a single match JSON. Returns True if saved."""
    fn = out / f"{mid}.json"
    if fn.exists():
        return False
    data = GET(session, f"matches/{mid}")
    fn.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser(description="Download high-MMR Dota 2 matches from OpenDota")
    ap.add_argument("--count",    type=int, default=1000, help="Number of matches to fetch")
    ap.add_argument("--min-rank", type=int, default=70,   help="Minimum avg_rank_tier")
    ap.add_argument("--api-key",  type=str,
                    default=os.getenv("OD_API_KEY", "").strip('"').strip("'"),
                    help="OpenDota API key (or set OD_API_KEY env var)")
    ap.add_argument("--out",      type=pathlib.Path, default=pathlib.Path("data/raw"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    key = args.api_key or None
    session = create_session(key)

    if key:
        print("✓ Using API key")
    else:
        print("⚠ No API key — rate limited to ~60 req/min", file=sys.stderr)

    # Phase 1: collect match IDs
    ids = collect_ids(session, args.count, args.min_rank)
    print(f"Collected {len(ids)} match IDs; downloading…")

    # Phase 2: download full match data
    saved = skipped = failed = 0
    for i, mid in enumerate(ids, 1):
        try:
            if save_match(session, mid, args.out):
                saved += 1
                print(f"  [{i}/{len(ids)}] saved {mid}")
            else:
                skipped += 1
        except Exception as exc:
            failed += 1
            print(f"  [{i}/{len(ids)}] SKIP {mid}: {exc}", file=sys.stderr)

    print(f"\n✓ Done — saved: {saved}  skipped (exists): {skipped}  failed: {failed}")


if __name__ == "__main__":
    main()
