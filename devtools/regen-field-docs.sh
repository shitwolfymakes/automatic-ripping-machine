#!/usr/bin/env bash
# Copy the field docs registry into the UI, which reads a committed copy
# (the same pattern as services/ui-neu/openapi.snapshot.json).
#
# CI's `codegen-ui-neu` job fails when the copy differs from
# packages/arm_common/arm_common/field_docs.json; rerun this after editing the
# registry and commit the result.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
SOURCE="${ROOT_DIR}/packages/arm_common/arm_common/field_docs.json"
TARGET="${ROOT_DIR}/services/ui-neu/frontend/src/lib/docs/field-docs.json"

mkdir -p "$(dirname -- "${TARGET}")"
cp -- "${SOURCE}" "${TARGET}"
echo "copied field_docs.json -> ${TARGET#"${ROOT_DIR}"/}"
