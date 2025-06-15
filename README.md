# Aegis Assistant

Aegis Assistant is a proof-of-concept tool that experiments with capturing Dota 2
Game State Integration (GSI) data and serving simple hints to a Tauri based
overlay. The repository contains several Python scripts for dataset preparation
and model serving as well as a minimal Tauri application used as the graphical
overlay.

## Repository layout

```
./scripts       – data collection, training and runtime helper scripts
./tauri-app     – small Tauri overlay that polls `/hint` from the Python server
```

Important scripts in `scripts/`:

- `fetch_matches.py` – downloads match JSON from OpenDota.
- `build_dataset.py` – transforms raw JSON into a CSV snapshot dataset.
- `train_model.py` – trains a LightGBM model using the dataset.
- `serve_model.py` – wraps a trained model with FastAPI.
- `gsi_server.py`   – minimal HTTP endpoint to collect live GSI packets.
- `mvp1_core.py`    – example runtime combining the GSI reader, model
  predictions and the overlay hint endpoint.

The `tauri-app` directory holds the UI code that fetches the current hint from
`http://127.0.0.1:5000/hint` and displays it in a small window.

## Quick start

1. Install the Python dependencies:

```bash
pip install -r requirements.txt
```

2. Run the model API (uses `data/models/aegis_lgbm_v3.pkl`):

```bash
python scripts/serve_model.py
```

3. In a separate terminal start the core server that handles GSI packets and
   exposes `/hint`:

```bash
python scripts/mvp1_core.py
```

4. Launch the Tauri app from `tauri-app/` (requires Node.js and the Tauri CLI).
It will periodically fetch the hint text and display it.

The repository also contains utilities for building datasets and training the
model from scratch. See the comments in each script for more details.

## Requirements

All Python dependencies are listed in `requirements.txt`.
