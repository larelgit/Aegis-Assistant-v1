#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve_model.py  –  FastAPI wrapper for Aegis Assistant model (fixed version)

Исправления:
1. /predict принимает произвольный JSON, а не строго заданную Pydantic-модель.
2. DataFrame формируется так, чтобы содержать ровно FEATURES – отсутствующие
   колонки заполняются нулями, лишние из запроса отбрасываются.
3. Удобный запуск через `python serve_model.py` (внутри вызывает uvicorn).
"""

from __future__ import annotations

from typing import Any, Dict, List
import pathlib

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException

# --------------------------------------------------------------------------- #
# ─── Загрузка модели / bundle ─────────────────────────────────────────────── #
PKL_PATH = pathlib.Path("data/models/aegis_lgbm_v3.pkl")
if not PKL_PATH.exists():
    raise FileNotFoundError(f"Model file not found: {PKL_PATH.resolve()}")

bundle = joblib.load(PKL_PATH)

if isinstance(bundle, dict) and "model" in bundle:          # «новый» формат
    model = bundle["model"]
    encoder = bundle.get("encoder")                         # может быть None
    FEATURES: List[str] = bundle.get("features") or []
else:                                                       # «старый» .pkl
    model = bundle
    encoder = None
    FEATURES = []

# если FEATURES в bundle нет – пробуем вытащить из самой модели
if not FEATURES:
    FEATURES = getattr(model, "feature_name_", [
        "gold_adv", "xp_adv", "our_dead_tot", "enemy_dead_tot"
    ])

# Список возможных меток (не используем, но оставляем для справки)
LABELS = encoder.classes_.tolist() if encoder else getattr(model, "classes_", [])

# --------------------------------------------------------------------------- #
app = FastAPI(title="Aegis Assistant – Model API")


def json_to_frame(payload: Dict[str, Any]) -> pd.DataFrame:
    """
    Превращаем входной JSON в DataFrame с нужными колонками:
    • отсутствующие колонки → 0
    • лишние колонки → отбрасываем
    """
    row = {f: payload.get(f, 0) for f in FEATURES}
    return pd.DataFrame([row], columns=FEATURES)


# --------------------------------------------------------------------------- #
@app.post("/predict")
def predict(payload: Dict[str, Any]):
    """
    Принимает JSON вида {"gold_adv": 123, ... } и возвращает:
        {"action": "FARM"}
    """
    try:
        df = json_to_frame(payload)
        y_pred = model.predict(df)[0]
        label = encoder.inverse_transform([y_pred])[0] if encoder else y_pred
        return {"action": str(label)}
    except Exception as exc:
        # Пробрасываем stack-trace в detail для более удобной отладки
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# ─── Локальный запуск ─────────────────────────────────────────────────────── #
if __name__ == "__main__":
    import uvicorn

    # Пример:  python serve_model.py
    uvicorn.run(app, host="0.0.0.0", port=8000)