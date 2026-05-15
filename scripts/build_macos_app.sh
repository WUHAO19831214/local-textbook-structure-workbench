#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m pip install -r backend/requirements.txt -r desktop/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build

python3 -m PyInstaller \
  --noconfirm \
  --windowed \
  --name "Local Textbook Workbench" \
  --paths backend \
  --collect-submodules uvicorn \
  --collect-submodules websockets \
  --collect-submodules httptools \
  --collect-submodules watchfiles \
  --collect-submodules anyio \
  --add-data "frontend/dist:frontend/dist" \
  desktop_app.py

echo "macOS app built at: $ROOT_DIR/dist/Local Textbook Workbench.app"
