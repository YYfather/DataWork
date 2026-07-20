from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for relative in [
    "src-tauri/tauri.conf.json",
    "src-tauri/capabilities/default.json",
    "package.json",
]:
    json.loads((ROOT / relative).read_text(encoding="utf-8"))
required = [
    "src-tauri/Cargo.toml",
    "src-tauri/src/lib.rs",
    "src-tauri/src/main.rs",
    "ui/index.html",
]
missing = [item for item in required if not (ROOT / item).exists()]
if missing:
    raise SystemExit(f"desktop scaffold missing: {missing}")
print("desktop scaffold OK")
