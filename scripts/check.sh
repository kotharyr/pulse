#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
python - <<'PY'
import json
from engineering_ops.config import configuration_report
report = configuration_report()
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["ok"] else 1)
PY
