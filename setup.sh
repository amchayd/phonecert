#!/usr/bin/env bash
# PhoneCert setup — run on your Mac: ./setup.sh
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "❌ python3 not found. Install: brew install python@3.12"; exit 1; }
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || { echo "❌ Python $PYV found, need 3.10+ (brew install python@3.12)"; exit 1; }
echo "✅ Python $PYV"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -e . -q
echo "✅ pymobiledevice3 + phonecert installed"

[ -d .git ] || { git init -q && git add . && git commit -qm "M0: project setup" && echo "✅ Git repo initialised"; }

echo ""
echo "Next:"
echo "  1. Plug in an iPhone, unlock it, tap 'Trust' and enter the passcode"
echo "  2. source .venv/bin/activate"
echo "  3. phonecert scan"
