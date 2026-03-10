#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve_model.py — FastAPI wrapper for the Aegis Assistant LightGBM model.

Endpoints:
  POST /predict  — predict macro-action from feature vector (with confidence)
  GET  /health   — model readiness check
  GET  /meta     — model metadata (features, classes)

Usage:
    python scripts/serve_model.py
    python scripts/serve_model.py --model data/models/aegis_lgbm_v3.pkl --port 8000
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import FEATURES as DEFAULT_FEATURES, DEFAULT_MODEL_PKL


# ─── Pydantic request schema (auto-generates OpenAPI docs) ───────────────── #

class PredictRequest(BaseModel):
    """Feature vector for macro-action prediction. All fields default to 0."""
    gold_adv: float           = Field(0, description="Gold advantage (positive = our team ahead)")
    xp_adv: float             = Field(0, description="XP advantage")
    our_dead_tot: int         = Field(0, ge=0, le=5, description="Dead allies")
    enemy_dead_tot: int       = Field(0, ge=0, le=5, description="Dead enemies")
    our_alive: int            = Field(0, ge=0, le=5, description="Alive allies")
    enemy_alive: int          = Field(0, ge=0, le=5, description="Alive enemies")
    our_core_alive: int       = Field(0, ge=0, le=2, description="Alive allied cores")
    enemy_core_alive: int     = Field(0, ge=0, le=2, description="Alive enemy cores")
    enemy_core_dead: int      = Field(0, ge=0, le=2, description="Dead enemy cores")
    roshan_alive: int         = Field(0, ge=0, le=1, description="1 if Roshan likely alive")
    recent_deaths: int        = Field(0, ge=0, description="Deaths in last 15 seconds")
    towers_dire_t3_down: int  = Field(0, ge=0, le=1, description="1 if enemy T3 tower destroyed")


class PredictResponse(BaseModel):
    action: str
    confidence: float
    probabilities: dict[str, float]


# ─── Model loading ────────────────────────────────────────────────────────── #

def load_model(pkl_path: pathlib.Path):
    """Load model bundle and return (model, encoder, features, labels)."""
    if not pkl_path.exists():
        print(f"✗ Model file not found: {pkl_path.resolve()}", file=sys.stderr)
        print(f"  Run `python scripts/train_model.py` first.", file=sys.stderr)
        sys.exit(1)

    bundle = joblib.load(pkl_path)

    if isinstance(bundle, dict) and "model" in bundle:
        model    = bundle["model"]
        encoder  = bundle.get("encoder")
        features = bundle.get("features")
    else:
        model    = bundle
        encoder  = None
        features = None

    # Validate features
    if not features:
        features = getattr(model, "feature_name_", None)
    if not features:
        print("✗ Cannot determine feature list from model bundle.", file=sys.stderr)
        print("  Ensure the bundle contains a 'features' key.", file=sys.stderr)
        sys.exit(1)

    # Determine class labels
    if encoder is not None:
        labels = list(encoder.classes_)
    else:
        labels = [str(c) for c in getattr(model, "classes_", [])]

    return model, encoder, features, labels


# ─── Module-level state (set during startup) ─────────────────────────────── #
MODEL = ENCODER = FEATURE_LIST = CLASS_LABELS = None  # type: ignore


# ─── FastAPI app ──────────────────────────────────────────────────────────── #

app = FastAPI(
    title="Aegis Assistant — Model API",
    description="LightGBM macro-action classifier for Dota 2",
    version="3.0",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": MODEL is not None,
        "n_features": len(FEATURE_LIST) if FEATURE_LIST else 0,
        "n_classes": len(CLASS_LABELS) if CLASS_LABELS else 0,
    }


@app.get("/meta")
def meta():
    return {
        "features": FEATURE_LIST,
        "classes": CLASS_LABELS,
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    """
    Predict macro-action from the current game state features.
    Returns action label, confidence, and per-class probabilities.
    """
    if MODEL is None:
        raise HTTPException(500, "Model not loaded")

    try:
        row = {f: getattr(req, f, 0) for f in FEATURE_LIST}
        df = pd.DataFrame([row], columns=FEATURE_LIST)

        proba = MODEL.predict_proba(df)[0]
        pred_idx = int(np.argmax(proba))
        confidence = float(proba[pred_idx])

        if ENCODER is not None:
            all_labels = list(ENCODER.classes_)
        else:
            all_labels = [str(c) for c in MODEL.classes_]

        label_name = all_labels[pred_idx]
        probabilities = {
            name: round(float(p), 4) for name, p in zip(all_labels, proba)
        }

        return PredictResponse(
            action=str(label_name),
            confidence=round(confidence, 4),
            probabilities=probabilities,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── Entry point ──────────────────────────────────────────────────────────── #

def main():
    ap = argparse.ArgumentParser(description="Serve Aegis LightGBM model via FastAPI")
    ap.add_argument("--model", type=pathlib.Path, default=DEFAULT_MODEL_PKL)
    ap.add_argument("--host",  default="0.0.0.0")
    ap.add_argument("--port",  type=int, default=8000)
    args = ap.parse_args()

    global MODEL, ENCODER, FEATURE_LIST, CLASS_LABELS
    MODEL, ENCODER, FEATURE_LIST, CLASS_LABELS = load_model(args.model)

    print(f"✓ Model loaded from {args.model}")
    print(f"  Features: {FEATURE_LIST}")
    print(f"  Classes:  {CLASS_LABELS}")

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
