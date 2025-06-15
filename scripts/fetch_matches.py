#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_matches.py  • v4  (June‑2025)

Скачивает N high‑MMR игр и сохраняет их JSON в data/raw/.

CLI:
  --count     <int>   (default 1000)
  --min-rank  <int>   avg_rank_tier threshold (default 70)
  --api-key   <str>   OpenDota API‑key (или перем. окруж. OD_API_KEY)
  --out       <dir>   куда класть .json (default data/raw)

Пример:
  $env:OD_API_KEY = e1c74fdf-c58a-4f09-b777-4b0937475907   # PowerShell
  python fetch_matches.py --count 3500 --min-rank 70
"""

from __future__ import annotations
import argparse, json, pathlib, time, os, sys, random, requests

OD_API = "https://api.opendota.com/api"

def GET(endpoint: str, api_key: str | None = None,
        params: dict | None = None, retry: int = 5):
    params = params.copy() if params else {}
    if api_key:
        params["api_key"] = api_key
    backoff = 2
    for attempt in range(1, retry + 1):
        r = requests.get(f"{OD_API}/{endpoint.lstrip('/')}", params=params, timeout=20)
        if r.status_code == 429:
            delay = backoff + random.random()
            print(f"[429] retry {attempt}/{retry} in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay); backoff *= 2; continue
        try:
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            if attempt == retry or r.status_code < 500:
                raise e
            delay = backoff + random.random()
            print(f"[{r.status_code}] retry in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay); backoff *= 2

def page_public_matches(less_than: int | None, key: str | None):
    params = {"less_than_match_id": less_than} if less_than else {}
    return GET("publicMatches", key, params)

def collect_ids(n: int, min_rank: int, key: str | None):
    ids, seen, last = [], set(), None
    while len(ids) < n:
        batch = page_public_matches(last, key)
        if not batch: break
        for m in batch:
            mid = m["match_id"]; last = mid
            if mid in seen: continue
            seen.add(mid)
            if m.get("avg_rank_tier", 0) >= min_rank:
                ids.append(mid)
                if len(ids) >= n: break
        time.sleep(0.5 if key else 1.1)      # throttle
    return ids

def save_match(mid: int, out: pathlib.Path, key: str | None):
    fn = out / f"{mid}.json"
    if fn.exists(): return
    data = GET(f"matches/{mid}", key)
    fn.write_text(json.dumps(data, indent=2))
    print("saved", mid)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count",     type=int, default=1000)
    ap.add_argument("--min-rank",  type=int, default=70)
    ap.add_argument("--api-key",   type=str,
                    default=os.getenv("OD_API_KEY", "").strip('"').strip("'"))
    ap.add_argument("--out",       type=pathlib.Path, default=pathlib.Path("data/raw"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.api_key:
        print("✓ using API‑key")
    else:
        print("⚠ no API‑key — будет лимит 60 rq/min", file=sys.stderr)

    ids = collect_ids(args.count, args.min_rank, args.api_key)
    print(f"collected {len(ids)} match ids; downloading…")

    for mid in ids:
        try:    save_match(mid, args.out, args.api_key)
        except Exception as e: print("skip", mid, e, file=sys.stderr)

if __name__ == "__main__":
    main()
