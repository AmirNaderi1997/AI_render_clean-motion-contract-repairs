#!/usr/bin/env bash
# Downloads the Linux wheels the effects engine needs (mediapipe and absl-py) into vendor/effects-wheels/, for servers that cannot reach PyPI.
# Install them in the runtime image with:  pip install --no-index --no-deps vendor/effects-wheels/*.whl
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p vendor/effects-wheels
python3 -m pip download --no-deps --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 \
  --python-version 3.12 --implementation cp --abi cp312 -d vendor/effects-wheels mediapipe absl-py
ls -la vendor/effects-wheels
