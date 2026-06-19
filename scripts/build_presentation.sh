#!/usr/bin/env bash
# One-shot regeneration of the final presentation deck + speaker-notes PDF.
#
#   scripts/build_presentation.sh
#
# Re-runnable. Builds the matplotlib charts, assembles the PPTX, and compiles the
# LaTeX speaker notes with tectonic. Streamlit screenshots are captured separately
# (they need a running app + Playwright) and committed under
# docs/presentation/charts/streamlit_*.png; this driver reuses them. To refresh
# them, set CAPTURE_SCREENSHOTS=1 (optionally STREAMLIT_URL=...).
set -euo pipefail

cd "$(dirname "$0")/.."
PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

echo "[1/4] data-viz charts (EDA, results, rebalancing, occupancy, map)"
PYTHONPATH=src "$PY" scripts/build_deck_charts.py

if [ "${CAPTURE_SCREENSHOTS:-0}" = "1" ]; then
  echo "[2/4] Streamlit screenshots"
  "$PY" scripts/capture_streamlit_screenshots.py --url "${STREAMLIT_URL:-http://127.0.0.1:8501}" \
    || echo "    (screenshot capture failed — reusing committed shots)"
else
  echo "[2/4] Streamlit screenshots — skipped (reusing committed shots; set CAPTURE_SCREENSHOTS=1 to refresh)"
fi

echo "[3/4] assemble deck -> docs/presentation/bixi_mlops_deck.pptx"
"$PY" scripts/build_deck.py

echo "[4/4] speaker notes -> docs/presentation/speaker_notes.pdf"
tectonic docs/presentation/speaker_notes.tex

echo "done:"
echo "  docs/presentation/bixi_mlops_deck.pptx"
echo "  docs/presentation/speaker_notes.pdf"
