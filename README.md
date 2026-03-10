# 🛡️ Aegis Assistant

> ML-powered macro-action advisor for Dota 2.
> Captures live Game State Integration data, predicts optimal team strategy
> via LightGBM, and displays hints in a minimal overlay.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Tauri](https://img.shields.io/badge/Tauri-Overlay-FFC131?logo=tauri)
![LightGBM](https://img.shields.io/badge/LightGBM-Classifier-000000)

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/larelgit/Aegis-Assistant-v1.git
cd Aegis-Assistant-v1
pip install -r requirements.txt
```

### 2. Start the Model API

```bash
python scripts/serve_model.py
```

> Loads `data/models/aegis_lgbm_v3.pkl` and serves predictions on port 8000.

### 3. Start the Runtime Server

```bash
python scripts/runtime_server.py
```

> Accepts Dota 2 GSI on port 5000, computes features, queries model, serves `/hint`.

### 4. Launch the Overlay

```bash
cd tauri-app
npm install
npm run tauri dev
```

### 5. (Optional) Configure Dota 2 GSI

Place this file in your Dota 2 config directory:
`steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/gamestate_integration_aegis.cfg`

```cfg
"Aegis Assistant"
{
    "uri"           "http://localhost:5000/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.2"
    "heartbeat"     "10.0"
    "data"
    {
        "map"           "1"
        "player"        "1"
        "allplayers"    "1"
        "buildings"     "1"
    }
}
```

---

## 🎮 Demo Without Dota 2

You don't need Dota 2 running to see the project in action:

```bash
# Terminal 1: Model API
python scripts/serve_model.py

# Terminal 2: Runtime server
python scripts/runtime_server.py

# Terminal 3: Replay synthetic game data
python scripts/replay_gsi.py --generate

# Terminal 4: Overlay
cd tauri-app && npm run tauri dev
```

The overlay will display changing hints as the synthetic game progresses.

---

## 📖 ML Pipeline

### 1. Fetch match data

```bash
python scripts/fetch_matches.py --count 1000 --min-rank 70
```

### 2. Build dataset

```bash
python scripts/build_dataset.py
```

### 3. Train model

```bash
python scripts/train_model.py
```

Evaluation artifacts are saved to `data/artifacts/`:
- `classification_report.txt`
- `confusion_matrix.csv`
- `feature_importance.csv`
- `metrics.json`

---

## 🏗️ Architecture

```
┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌─────────┐
│ OpenDota │────▸│ build_dataset│────▸│  train_model   │────▸│  .pkl   │
│   API    │     │    .py       │     │     .py        │     │ bundle  │
└──────────┘     └──────────────┘     └───────────────┘     └────┬────┘
                                                                  │
┌──────────┐     ┌──────────────┐     ┌───────────────┐          │
│  Dota 2  │────▸│   runtime    │────▸│  serve_model  │◂─────────┘
│   GSI    │     │  _server.py  │     │     .py       │
└──────────┘     └──────┬───────┘     └───────────────┘
                        │
                 ┌──────▼───────┐
                 │ Tauri overlay│
                 │   /hint      │
                 └──────────────┘
```

---

## 📁 Project Structure

```
├── scripts/
│   ├── config.py            # Shared constants, feature/label definitions
│   ├── fetch_matches.py     # Download matches from OpenDota
│   ├── build_dataset.py     # Raw JSON → labeled CSV snapshots
│   ├── train_model.py       # Train LightGBM + save artifacts
│   ├── serve_model.py       # FastAPI model API (port 8000)
│   ├── runtime_server.py    # GSI receiver + hint server (port 5000)
│   ├── replay_gsi.py        # Demo mode: replay/generate GSI packets
│   ├── record_gsi.py        # Debug: standalone GSI packet recorder
│   └── screenshot.py        # Experimental: minimap capture (optional)
├── tauri-app/               # Minimal overlay UI
├── tests/                   # Unit and smoke tests
├── data/
│   ├── raw/                 # Downloaded match JSONs (gitignored)
│   ├── snapshots/           # Generated CSV datasets (gitignored)
│   ├── models/              # Trained model bundles
│   └── artifacts/           # Evaluation reports and metrics
├── requirements.txt
└── requirements-dev.txt
```

---

## ⚙️ API Endpoints

### Model API (port 8000)

| Method | Endpoint   | Description                         |
|--------|-----------|-------------------------------------|
| POST   | `/predict` | Predict macro-action from features |
| GET    | `/health`  | Model readiness check              |
| GET    | `/meta`    | Feature list, class labels         |

### Runtime Server (port 5000)

| Method | Endpoint          | Description                    |
|--------|-------------------|-------------------------------|
| POST   | `/gsi`            | Receive Dota 2 GSI packet     |
| GET    | `/hint`           | Current hint for overlay      |
| GET    | `/health`         | Server + model API status     |
| GET    | `/debug/state`    | Raw last GSI payload          |
| GET    | `/debug/features` | Last computed feature vector  |

---

## ⚠️ Known Limitations

- **Heuristic labels**: training data uses rule-based labels, not human annotations
- **Radiant-centric training**: model is trained from Radiant perspective; runtime inverts features for Dire players
- **Roshan respawn**: approximated with fixed 8-min window (real: 8–11 min random)
- **Tower status in training**: reconstructed from match objectives; may be absent for some matches
- **Local only**: no cloud deployment, single-machine setup
- **No input automation**: advisory only, does not interact with the game

---

## 🧪 Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
