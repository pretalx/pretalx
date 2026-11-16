#!/usr/bin/env bash
# Run the plugin tests inside the pretalx image, against this source tree.
#   ./run-tests.sh [pytest args]     e.g. ./run-tests.sh -k callback -x
set -euo pipefail
cd "$(dirname "$0")"
IMAGE="${IMAGE:-pretalx-sso:latest}"
exec docker run --rm \
    -v "$PWD":/plugin-src:ro \
    -e PYTHONPATH=/plugin-src \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -w /plugin-src \
    --entrypoint bash "$IMAGE" -c \
    'pip3 install -q --disable-pip-version-check --no-deps --target /tmp/testdeps -r tests/requirements.txt >/dev/null \
     && PYTHONPATH=/plugin-src:/tmp/testdeps python3 -m pytest "$@"' _ "$@"
