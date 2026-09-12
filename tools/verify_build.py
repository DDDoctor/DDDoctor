"""校验 PyInstaller 输出是否完整（防止被文件锁搞成半成品）。

    .venv\\Scripts\\python.exe tools\\verify_build.py dist_final\\MultiView
"""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = [
    "MultiView.exe",
    "_internal/python313.dll",
    "_internal/vlc/libvlc.dll",
    "_internal/vlc/libvlccore.dll",
    "_internal/vlc/plugins",
    "_internal/PySide6/plugins/platforms/qwindows.dll",
    "_internal/PySide6/QtCore.pyd",
    "_internal/PySide6/QtGui.pyd",
    "_internal/PySide6/QtWidgets.pyd",
]

MIN_FILES = 400
MIN_MB = 200


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/MultiView")
    if not root.is_dir():
        print(f"[FAIL] 目录不存在: {root}")
        return 1

    files = [p for p in root.rglob("*") if p.is_file()]
    total_mb = sum(p.stat().st_size for p in files) / 1024 / 1024
    print(f"目录: {root}")
    print(f"文件数: {len(files)}   体积: {total_mb:.1f} MB")

    ok = True
    for item in REQUIRED:
        exists = (root / item).exists()
        print(f"  {'OK  ' if exists else '缺失'}  {item}")
        ok = ok and exists

    plugins = root / "_internal" / "vlc" / "plugins"
    n_plugins = len([p for p in plugins.rglob("*") if p.is_file()]) if plugins.is_dir() else 0
    print(f"  VLC 插件文件数: {n_plugins}")

    if len(files) < MIN_FILES:
        print(f"[FAIL] 文件数偏少（< {MIN_FILES}），打包很可能不完整")
        ok = False
    if total_mb < MIN_MB:
        print(f"[FAIL] 体积偏小（< {MIN_MB} MB），打包很可能不完整")
        ok = False
    if n_plugins < 200:
        print("[FAIL] VLC 插件不完整")
        ok = False

    print("[PASS] 构建完整" if ok else "[FAIL] 构建不完整！")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
