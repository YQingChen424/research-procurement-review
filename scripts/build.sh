#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src
mkdir -p dist
python - <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path.cwd()
with ZipFile(root / "dist/research-procurement-review.zip", "w", ZIP_DEFLATED) as archive:
    for folder in ("src", "config", "data", "docs", "examples", "scripts"):
        for path in (root / folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                archive.write(path, path.relative_to(root))
    for name in ("README.md", "LICENSE", "requirements.txt"):
        archive.write(root / name, name)
PY
