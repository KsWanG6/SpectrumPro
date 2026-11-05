#!/bin/bash
# Build SpectrumPro.app for the Mac you are running on (Apple Silicon -> arm64, Intel -> x86_64).
# Usage:  cd app && bash packaging/macos/build_mac.sh
set -e
cd "$(dirname "$0")/../.."
ARCH=$(uname -m)                                  # arm64 | x86_64
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null; then echo "找不到 python3。請先安裝 Python 3.10–3.12（python.org 或 brew install python）"; exit 1; fi
echo "== 架構: $ARCH   Python: $($PY --version) =="
[ -d .buildenv_mac ] || "$PY" -m venv .buildenv_mac
. .buildenv_mac/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller pillow
rm -rf build dist
python -m PyInstaller --noconfirm --windowed --name SpectrumPro \
  --icon packaging/macos/spectrumpro.icns \
  --osx-bundle-identifier com.kuansyunwang.spectrumpro \
  --add-data "ramanproc/assets:ramanproc/assets" \
  run_gui.py
# Ad-hoc signature (required for arm64 apps to launch at all; not a paid Developer-ID signature)
codesign --force --deep --sign - dist/SpectrumPro.app
ditto -c -k --keepParent dist/SpectrumPro.app "dist/SpectrumPro-macos-$ARCH.zip"
echo
echo "完成： dist/SpectrumPro.app   以及   dist/SpectrumPro-macos-$ARCH.zip"
echo "這個版本只能在 $ARCH 的 Mac 上執行（另一種晶片請在對應的 Mac 或 GitHub Actions 上再建一次）。"
