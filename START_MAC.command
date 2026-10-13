#!/bin/bash
cd "$(dirname "$0")" || exit 1
# Apple Silicon Homebrew defaults to /opt/homebrew; Intel typically uses /usr/local.
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "VDODesk needs FFmpeg. On Apple Silicon (M4), run:"
  echo "  /opt/homebrew/bin/brew install ffmpeg"
  echo "If Homebrew is not installed, visit https://brew.sh/ first."
  read -r -p 'Press Enter to close...'
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing; install via Homebrew: brew install python"
  read -r -p 'Press Enter to close...'
  exit 1
fi
echo "Starting VDODesk on Apple Silicon / macOS..."
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi
"$PYTHON_BIN" app/server.py
code=$?
if [ "$code" -ne 0 ]; then read -r -p 'Press Enter to close...'; fi
exit "$code"
