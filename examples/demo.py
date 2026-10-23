"""Run the fabricated sample without a shell-specific PYTHONPATH setting."""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from my_tool.core.review import review_batch  # noqa: E402
from my_tool.utils.files import load_json  # noqa: E402

result = review_batch(load_json(ROOT / "data/sample_requests.json"), as_of=date(2026, 10, 23))
print(json.dumps(result, ensure_ascii=False, indent=2))
