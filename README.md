# 🛡️ Aegis Assistant

> Proof-of-concept assistant for Dota 2.  
> Captures live Game State Integration (GSI) data and serves machine learning-driven hints to a sleek overlay.

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![Tauri](https://img.shields.io/badge/Tauri-App-FFC131?logo=tauri)
![LightGBM](https://img.shields.io/badge/LightGBM-ML-000000)

---

## 🚀 Quick start

### 1. Clone the repository

```bash
git clone https://github.com/larelgit/Aegis-Assistant-v1.git
cd Aegis-Assistant-v1
```

### 2. Install dependencies

All Python requirements are handled via `pip`. You will also need Node.js and the Tauri CLI installed for the overlay.

```bash
pip install -r requirements.txt
```

### 3. Start the Model API

Run the serving script (defaults to using the pre-trained `data/models/aegis_lgbm_v3.pkl` model):

```bash
python scripts/serve_model.py
```

### 4. Start the Core GSI Server

In a **separate terminal**, start the core server. This handles live Dota 2 GSI packets, queries the model, and exposes the `/hint` endpoint:

```bash
python scripts/mvp1_core.py
```

### 5. Launch the Overlay

In a **third terminal**, launch the Tauri application. It will periodically fetch the current hint from `http://127.0.0.1:5000/hint` and display it in a minimal, overlay-friendly window.

```bash
cd tauri-app
npm install
npm run tauri dev
```

---

## 📖 Usage (ML Pipeline)

The repository contains a full suite of utilities for building datasets and training the LightGBM model from scratch. See comments inside each script for deep-dives.

### 1. Fetch match data

Downloads raw match JSON data from OpenDota.

```bash
python scripts/fetch_matches.py
```

### 2. Build the dataset

Transforms the raw match JSONs into a structured CSV snapshot dataset.

```bash
python scripts/build_dataset.py
```

### 3. Train the model

Trains a LightGBM model using the generated dataset and saves it to the `data/models/` directory.

```bash
python scripts/train_model.py
```

---

## 📁 Project structure

```text
├── scripts/                 # Data collection, ML, and runtime scripts
│   ├── fetch_matches.py     # Downloads match JSON from OpenDota
│   ├── build_dataset.py     # Transforms raw JSON into a CSV snapshot
│   ├── train_model.py       # Trains a LightGBM model
│   ├── serve_model.py       # Wraps the trained model with FastAPI
│   ├── gsi_server.py        # Minimal HTTP endpoint to collect live GSI packets
│   └── mvp1_core.py         # Combines GSI reader, ML predictions & hint overlay
├── tauri-app/               # Minimal Tauri UI overlay fetching hints
├── data/                    
│   └── models/              # Saved model weights (e.g., aegis_lgbm_v3.pkl)
└── requirements.txt         # Python dependencies
```

---

## ⚙️ Requirements

- **Backend / ML**: Python 3.8+
- **Frontend / Overlay**: Node.js, npm/yarn/pnpm, and Tauri CLI
- **Dota 2**: Game State Integration (GSI) configured in your Dota 2 client.
