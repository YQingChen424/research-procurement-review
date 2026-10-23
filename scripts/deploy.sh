#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
target="${1:?Usage: scripts/deploy.sh LOCAL_DIRECTORY}"
bash scripts/build.sh
mkdir -p "$target"
cp dist/research-procurement-review.zip "$target/"
printf 'Copied local archive to %s\n' "$target"
