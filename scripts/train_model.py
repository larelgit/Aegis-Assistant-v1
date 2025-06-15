#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Train LightGBM multiclass on ideal_no_pos.csv
– group-aware split (no leakage)
– balanced classes
– stores model + LabelEncoder + feature list
"""

import joblib, pathlib, argparse
import pandas as pd, lightgbm as lgb
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix

# ---------- CLI -------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument("--csv",   type=pathlib.Path,
                default=pathlib.Path("data/snapshots/ideal_no_pos.csv"))
ap.add_argument("--model", type=pathlib.Path,
                default=pathlib.Path("data/models/aegis_lgbm.pkl"))
ap.add_argument("--test-size", type=float, default=0.2)
args = ap.parse_args()
args.model.parent.mkdir(parents=True, exist_ok=True)

# ---------- Load & split ----------------------------------------------------
df = pd.read_csv(args.csv)

labels = df["label"]
groups = df["match_id"]

le = LabelEncoder()
y = le.fit_transform(labels)

# drop tech cols
X = df.drop(columns=["label", "match_id", "t"])

gss = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=42)
train_idx, val_idx = next(gss.split(X, y, groups))

X_train, y_train = X.iloc[train_idx], y[train_idx]
X_val,   y_val   = X.iloc[val_idx],   y[val_idx]

# ---------- Model -----------------------------------------------------------
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
    random_state=42,
)

model.fit(X_train, y_train)

# ---------- Evaluation ------------------------------------------------------
pred = model.predict(X_val)
print(classification_report(y_val, pred, target_names=le.classes_))
print("Confusion matrix:\n", confusion_matrix(y_val, pred))

# ---------- Save bundle -----------------------------------------------------
bundle = dict(model=model,
              encoder=le,
              features=list(X.columns))
joblib.dump(bundle, args.model)
print("✓ model saved →", args.model, "| classes:", list(le.classes_))
