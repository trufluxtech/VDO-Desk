#!/bin/bash
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Install Python first: brew install python"
  read -r -p 'Press Enter to close...'
  exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-advanced.txt
echo "Advanced OpenCV tracking is installed. START_MAC.command will use it automatically."
read -r -p 'Press Enter to close...'
