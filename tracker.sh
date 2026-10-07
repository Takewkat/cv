#!/usr/bin/env bash
# Starts the job-application tracker on 127.0.0.1 and opens it in the browser on macOS (prints the URL elsewhere).
# Usage: ./tracker.sh                          -> data in tracker/data/applications.json
#        ./tracker.sh --data ~/Drive/tracker   -> data in that folder (or file); same as TRACKER_DATA=<path>
#        ./tracker.sh --port 9000
#        ./tracker.sh --export-csv applications.csv   -> writes the board as CSV and exits
set -euo pipefail

command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }
exec python3 "$(dirname "$0")/tracker/server.py" --open "$@"
