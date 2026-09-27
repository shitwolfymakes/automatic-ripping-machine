#!/usr/bin/env bash
# Regenerate services/ui-neu/openapi.snapshot.json from the live FastAPI app.
#
# CI's `openapi-drift` job fails when the snapshot diverges from
# `arm_backend.main:app.openapi()`. This script is the canonical fix —
# rerun it after any change to backend routers / arm_common schemas
# that affects the wire contract, and commit the new snapshot.
#
# After regenerating, the UI's codegen also needs to be rerun
# (services/ui-neu/scripts/codegen.sh) so the generated TS types follow.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
SNAPSHOT="${ROOT_DIR}/services/ui-neu/openapi.snapshot.json"

# Settings has two required fields: DATABASE_URL and ARM_SERVICE_TOKEN.
# Neither is touched during openapi computation — pass dummies so the
# pydantic-settings constructor doesn't fail.
export ARM_SERVICE_TOKEN="${ARM_SERVICE_TOKEN:-regen-dummy-token}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://x:x@localhost/x}"
export ARM_LOG_LEVEL="${ARM_LOG_LEVEL:-warning}"

cd "${ROOT_DIR}"

echo "→ generating live OpenAPI from arm_backend.main:app"
uv run python - >"${SNAPSHOT}" <<'PY'
import json
from arm_backend.main import app

print(json.dumps(app.openapi(), indent=2))
PY

echo "→ wrote ${SNAPSHOT}"

# Regenerate UI types if the UI is set up.
if [[ -d "${ROOT_DIR}/services/ui-neu/frontend/node_modules" ]]; then
    echo "→ regenerating UI TypeScript types (services/ui-neu/scripts/codegen.sh)"
    bash "${ROOT_DIR}/services/ui-neu/scripts/codegen.sh"
else
    echo "✱ UI node_modules absent; skipping api.gen.ts codegen."
    echo "  Run 'npm ci --prefix services/ui-neu/frontend' then 'bash services/ui-neu/scripts/codegen.sh' to refresh."
fi
