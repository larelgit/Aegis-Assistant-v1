#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py — shared constants for Aegis Assistant.

Single source of truth for feature names, label mappings, paths, and ports.
"""

from pathlib import Path

# ─── Feature vector (12 features, Radiant-centric in training) ────────────── #
FEATURES: list[str] = [
    "gold_adv",
    "xp_adv",
    "our_dead_tot",
    "enemy_dead_tot",
    "our_alive",
    "enemy_alive",
    "our_core_alive",
    "enemy_core_alive",
    "enemy_core_dead",
    "roshan_alive",
    "recent_deaths",
    "towers_dire_t3_down",
]

# ─── All possible macro-action labels ─────────────────────────────────────── #
LABELS: list[str] = [
    "FARM",
    "STACK",
    "GANK",
    "PUSH",
    "DEFEND",
    "TEAMFIGHT",
    "TAKE_ROSHAN",
    "CONTEST_ROSHAN",
    "SIEGE",
]

LABEL2TXT: dict[str, str] = {
    "FARM":             "💰 Farm",
    "STACK":            "📦 Stack",
    "GANK":             "🗡️ Gank",
    "PUSH":             "⚔️ Push",
    "DEFEND":           "🛡️ Defend",
    "TEAMFIGHT":        "🔥 Teamfight",
    "TAKE_ROSHAN":      "🐻 Take Roshan",
    "CONTEST_ROSHAN":   "👀 Contest Roshan",
    "SIEGE":            "🏰 Siege",
}

# ─── Default paths ────────────────────────────────────────────────────────── #
DEFAULT_RAW_DIR      = Path("data/raw")
DEFAULT_DATASET_CSV  = Path("data/snapshots/dataset_v3.csv")
DEFAULT_MODEL_PKL    = Path("data/models/aegis_lgbm_v3.pkl")
DEFAULT_ARTIFACTS    = Path("data/artifacts")

# ─── Network ──────────────────────────────────────────────────────────────── #
MODEL_API_URL  = "http://127.0.0.1:8000"
RUNTIME_HOST   = "0.0.0.0"
RUNTIME_PORT   = 5000
MODEL_HOST     = "0.0.0.0"
MODEL_PORT     = 8000
