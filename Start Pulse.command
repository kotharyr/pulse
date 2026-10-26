#!/bin/bash
# Finder opens .command files in Terminal. All paths are relative to this file.
set -eu
PULSE_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ -n "${PULSE_PYTHON:-}" ]; then
    PULSE_BOOTSTRAP="$PULSE_PYTHON"
else
    PULSE_BOOTSTRAP=""
    for candidate in python3.12 python3.13 python3.14 python3.11 \
        "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3.12" \
        python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PULSE_BOOTSTRAP="$(command -v "$candidate")"
            break
        fi
    done
fi

if [ -z "$PULSE_BOOTSTRAP" ]; then
    echo "Pulse needs Python 3.11 or newer. Install Python, then open this file again."
    read -r -p "Press Return to close. " _
    exit 1
fi

if "$PULSE_BOOTSTRAP" "$PULSE_ROOT/scripts/start_pulse.py" "$@"; then
    exit 0
else
    result=$?
    echo
    read -r -p "Press Return to close. " _
    exit "$result"
fi
