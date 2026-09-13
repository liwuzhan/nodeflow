#!/usr/bin/env bash
# Authoritative NodeFlow test entrypoint.
# Usage: ./tools/run_tests.sh [quick|full|collect|preflight]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

MODE="${1:-quick}"

case "${MODE}" in
    quick)
        python3 -m pytest -q tests/unit cloud/server/tests
        ;;
    full)
        python3 -m pytest -q
        ;;
    collect)
        python3 -m pytest --collect-only -q
        ;;
    preflight)
        python3 -m tools.preflight_runtime
        ;;
    *)
        echo "Unknown mode: ${MODE}" >&2
        echo "Usage: $0 [quick|full|collect|preflight]" >&2
        exit 2
        ;;
esac
