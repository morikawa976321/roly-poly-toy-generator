from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python backend/scripts/export_openapi.py <output_path>", file=sys.stderr)
        return 2

    out_path = Path(sys.argv[1]).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure repo root is on sys.path so `import backend.*` works
    # even when executed from the `frontend/` directory.
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))

    # Importing the app builds the FastAPI instance (and loads env).
    from backend.app.main import app  # noqa: WPS433

    spec = app.openapi()
    out_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI spec to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
