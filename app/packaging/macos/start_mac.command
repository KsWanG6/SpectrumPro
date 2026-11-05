#!/bin/bash
# Run SpectrumPro from source (no packaging). Needs Python 3.10–3.12. Double-click in Finder.
cd "$(dirname "$0")/../.."
[ -d .venv ] || { python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt; }
. .venv/bin/activate
python run_gui.py "$@"
