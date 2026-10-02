#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WSP_ROOT="${WSP_ROOT:-"$ROOT/../wam-silent-payments"}"

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "FAIL: Python 3 is required."
  exit 1
fi

"$PYTHON" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"; print("Python:", sys.version.split()[0])'

if [ ! -f "$WSP_ROOT/pyproject.toml" ] && [ ! -f "$WSP_ROOT/setup.py" ]; then
  echo "FAIL: WSP-1 repository not found at: $WSP_ROOT"
  echo "Clone it as a sibling repository:"
  echo "git clone -b feat/wsp1-v1.0 https://github.com/Urriki1502/wam-silent-payments.git ../wam-silent-payments"
  exit 1
fi

SDK_ROOT="$WSP_ROOT/integration-deps/wam-sdk"
[ -d "$SDK_ROOT" ] || { echo "FAIL: WAM SDK not found: $SDK_ROOT"; exit 1; }

[ -d "$ROOT/.venv" ] || "$PYTHON" -m venv "$ROOT/.venv"
VENV_PY="$ROOT/.venv/bin/python"

"$VENV_PY" -m pip install --upgrade pip setuptools wheel
"$VENV_PY" -m pip install --no-build-isolation -e "$WSP_ROOT"
"$VENV_PY" -m pip install --no-build-isolation -e "$SDK_ROOT"
"$VENV_PY" -m pip install --no-build-isolation -e "$ROOT"
"$VENV_PY" -c 'import PySide6, wam_sp, wam_sdk, wam_silent_wallet; print("IMPORT CHECK: PASS")'

echo "BOOTSTRAP: PASS"
echo "Run: source .venv/bin/activate && python app.py"
