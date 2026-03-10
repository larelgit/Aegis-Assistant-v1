#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_model.py — Train LightGBM multiclass classifier for Aegis Assistant.

Features:
  • Group-aware train/val split (no leakage across matches)
  • Balanced class weights
  • Saves bundle: model + LabelEncoder + feature list
  • Saves evaluation artifacts: report, confusion matrix, feature importance
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import joblib
import pandas as pd
import lightgbm as lgb
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix

from config import DEFAULT_DATASET_CSV, DEFAULT_MODEL_PKL, DEFAULT_ARTIFACTS


def main():
    # ─── CLI ──────────────────────────────────────────────────────────────── #
    ap = argparse.ArgumentParser(description="Train LightGBM model for Aegis Assistant")
    ap.add_argument("--csv",       type=pathlib.Path, default=DEFAULT_DATASET_CSV)
    ap.add_argument("--model",     type=pathlib.Path, default=DEFAULT_MODEL_PKL)
    ap.add_argument("--artifacts", type=pathlib.Path, default=DEFAULT_ARTIFACTS)
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--seed",      type=int, default=42)
    args = ap.parse_args()

    args.model.parent.mkdir(parents=True, exist_ok=True)
    args.artifacts.mkdir(parents=True, exist_ok=True)

    # ─── Load ─────────────────────────────────────────────────────────────── #
    if not args.csv.exists():
        print(f"✗ Dataset not found: {args.csv}", file=sys.stderr)
        print(f"  Run `python scripts/build_dataset.py` first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(args.csv)
    print(f"Loaded {len(df):,} rows from {args.csv}")

    labels = df["label"]
    groups = df["match_id"]

    le = LabelEncoder()
    y = le.fit_transform(labels)

    # Drop non-feature columns
    X = df.drop(columns=["label", "match_id", "t"])
    feature_names = list(X.columns)

    print(f"Features ({len(feature_names)}): {feature_names}")
    print(f"Classes  ({len(le.classes_)}):  {list(le.classes_)}")

    # ─── Split (group-aware) ──────────────────────────────────────────────── #
    gss = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=args.seed)
    train_idx, val_idx = next(gss.split(X, y, groups))

    X_train, y_train = X.iloc[train_idx], y[train_idx]
    X_val,   y_val   = X.iloc[val_idx],   y[val_idx]

    print(f"Train: {len(X_train):,}  |  Val: {len(X_val):,}")

    # ─── Model ────────────────────────────────────────────────────────────── #
    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(le.classes_),
        n_estimators=800,
        max_depth=-1,
        learning_rate=0.05,
        class_weight="balanced",
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,
        random_state=args.seed,
        verbosity=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(50, verbose=True), lgb.log_evaluation(100)],
    )

    # ─── Evaluation ───────────────────────────────────────────────────────── #
    pred = model.predict(X_val)

    report_str = classification_report(y_val, pred, target_names=le.classes_)
    cm = confusion_matrix(y_val, pred)

    print("\n" + report_str)
    print("Confusion matrix:\n", cm)

    # ─── Save artifacts ───────────────────────────────────────────────────── #
    # 1. Classification report
    (args.artifacts / "classification_report.txt").write_text(report_str, encoding="utf-8")

    # 2. Confusion matrix
    cm_df = pd.DataFrame(cm, index=le.classes_, columns=le.classes_)
    cm_df.to_csv(args.artifacts / "confusion_matrix.csv")

    # 3. Feature importance
    importance = pd.DataFrame({
        "feature": feature_names,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    importance.to_csv(args.artifacts / "feature_importance.csv", index=False)

    # 4. Metrics summary
    from sklearn.metrics import accuracy_score, f1_score
    metrics = {
        "accuracy": round(accuracy_score(y_val, pred), 4),
        "macro_f1": round(f1_score(y_val, pred, average="macro"), 4),
        "weighted_f1": round(f1_score(y_val, pred, average="weighted"), 4),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_features": len(feature_names),
        "n_classes": len(le.classes_),
        "classes": list(le.classes_),
        "best_iteration": model.best_iteration_ if hasattr(model, "best_iteration_") else None,
    }
    (args.artifacts / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n✓ Artifacts saved → {args.artifacts}/")
    print(f"  • classification_report.txt")
    print(f"  • confusion_matrix.csv")
    print(f"  • feature_importance.csv")
    print(f"  • metrics.json")

    # ─── Save model bundle ────────────────────────────────────────────────── #
    bundle = dict(
        model=model,
        encoder=le,
        features=feature_names,
    )
    joblib.dump(bundle, args.model)
    print(f"\n✓ Model saved → {args.model}")
    print(f"  Classes: {list(le.classes_)}")
    print(f"  Accuracy: {metrics['accuracy']}  |  Macro-F1: {metrics['macro_f1']}")


if __name__ == "__main__":
    main()
