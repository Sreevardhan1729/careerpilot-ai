"""Write the OpenAPI document to a file (used by the frontend type generator). Usage: python scripts/export_openapi.py OUT"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("TASK_RUNNER_ENABLED", "false")

from app.main import create_app  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
out.write_text(json.dumps(create_app().openapi(), indent=2))
print(f"wrote {out}")
