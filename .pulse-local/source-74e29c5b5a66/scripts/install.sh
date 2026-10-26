#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"

[ -f .env ] || cp .env.example .env
[ -f config/jira_instances.json ] || cp config/jira_instances.example.json config/jira_instances.json

echo "Installed successfully."
echo "Next: edit .env and config/jira_instances.json, then run ./scripts/run.sh"
