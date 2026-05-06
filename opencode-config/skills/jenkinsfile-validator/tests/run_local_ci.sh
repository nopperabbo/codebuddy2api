#!/usr/bin/env bash

# Local CI entrypoint for jenkinsfile-validator regressions.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$TEST_DIR/.." && pwd)"
REGRESSION_TEST="$SKILL_DIR/tests/test_validate_jenkinsfile.sh"

shell_files=()
for file in "$SKILL_DIR"/scripts/*.sh "$SKILL_DIR"/tests/*.sh; do
    if [ -f "$file" ]; then
        shell_files+=("$file")
    fi
done

if [ "${#shell_files[@]}" -eq 0 ]; then
    echo "ERROR: no shell files found for syntax checks"
    exit 2
fi

echo "Running shell syntax checks..."
bash -n "${shell_files[@]}"

echo "Running regression suite..."
bash "$REGRESSION_TEST"

echo "PASS: jenkinsfile-validator local CI checks"
