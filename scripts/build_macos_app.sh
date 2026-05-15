#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .desktop-venv
source .desktop-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt -r desktop/requirements.txt
npm --prefix frontend install
npm --prefix frontend run build

python -m PyInstaller \
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

APP_PATH="$ROOT_DIR/dist/Local Textbook Workbench.app"

if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$APP_PATH"
  xattr -d com.apple.FinderInfo "$APP_PATH" 2>/dev/null || true
  xattr -d com.apple.FinderInfo "$APP_PATH/Contents/Frameworks/Python3.framework" 2>/dev/null || true
  xattr -d -s com.apple.FinderInfo "$APP_PATH/Contents/Resources/Python3.framework" 2>/dev/null || true
fi

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_PATH" || true
fi

echo "macOS app built at: $APP_PATH"
