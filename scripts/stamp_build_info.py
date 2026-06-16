from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/stamp_build_info.py <release-tag>", file=sys.stderr)
        return 2

    release_tag = sys.argv[1].strip()
    if not release_tag:
        print("release tag is required", file=sys.stderr)
        return 2

    project_root = Path(__file__).resolve().parents[1]
    build_info_path = project_root / "src" / "email_order_reader" / "build_info.py"
    build_info_path.write_text(
        f"CURRENT_RELEASE_TAG = {json.dumps(release_tag)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
