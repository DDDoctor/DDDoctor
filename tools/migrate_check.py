"""验证「目录设置」的迁移：旧配置里的绝对路径应被改成相对路径。

    .venv\\Scripts\\python.exe tools\\migrate_check.py [旧配置.json]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import AppConfig  # noqa: E402


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "config.user-backup.json")
    if not src.is_file():
        print(f"找不到 {src}")
        return 1

    before = AppConfig.load_raw_dirs(src) if hasattr(AppConfig, "load_raw_dirs") else None
    print(f"=== 原始配置 {src} ===")
    import json

    raw = json.loads(src.read_text(encoding="utf-8-sig"))
    print(f"  snapshot_dir = {raw.get('snapshot_dir')}")
    print(f"  record_dir   = {raw.get('record_dir')}")

    cfg = AppConfig.load(src)
    print("=== 载入（自动迁移）后 ===")
    print(f"  snapshot_dir = {cfg.snapshot_dir!r}   ->  {cfg.snapshot_dir_display()}")
    print(f"  record_dir   = {cfg.record_dir!r}   ->  {cfg.record_dir_display()}")

    out = ROOT / "build_cache" / "migrated_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg.save(out)
    print(f"=== 已写出迁移结果 {out} ===")

    ok = not Path(cfg.record_dir).is_absolute() and not Path(cfg.snapshot_dir).is_absolute()
    print("[PASS] 目录已改为相对路径，换版本/挪目录都会跟随" if ok else "[??] 仍是绝对路径")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
