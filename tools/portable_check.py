"""把分发包解压到临时目录跑一遍，确认「换目录也能用」且录制目录跟随程序位置。

    .venv\\Scripts\\python.exe tools\\portable_check.py dist_v105\\MultiView-1.0.5-win64.zip
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.hang_probe import find_window, list_windows, user32  # noqa: E402

WM_CLOSE = 0x0010


def main() -> int:
    zip_path = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/MultiView-1.0.4-win64.zip")
    if not zip_path.is_absolute():
        zip_path = ROOT / zip_path
    dest = ROOT / "build_cache" / "portable"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    print(f"解压 {zip_path.name} -> {dest}")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        has_config = any(n.endswith("MultiView/config.json") for n in names)
        print(f"  条目 {len(names)}   内含 config.json: {has_config}（应为 False）")
        zf.extractall(dest)

    exe = dest / "MultiView" / "MultiView.exe"
    if not exe.is_file():
        print("[FAIL] 解压后找不到 MultiView.exe")
        return 1

    print("启动（脱离父进程）…")
    subprocess.run(["cmd", "/c", "start", "", str(exe)], check=False)
    time.sleep(14)

    found = list_windows()
    ours = [w for w in found if "视频墙" in w[1]]
    if not ours:
        print("[FAIL] 没有找到程序窗口")
        return 1
    hwnd, title, pid = ours[0]
    print(f"  窗口: {title}   pid={pid}")

    log = dest / "MultiView" / "multiview.log"
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if "input-record-path" in line or "VLC 运行库目录" in line:
                print("  " + line.split("INFO", 1)[-1].strip()[:170])

    rec = dest / "MultiView" / "recordings"
    print(f"  录制目录是否建在程序目录下: {rec.is_dir()}  -> {rec}")

    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    print("  已发送关闭")
    deadline = time.time() + 20
    while time.time() < deadline:
        if not [w for w in list_windows() if w[2] == pid]:
            print("  已退出")
            break
        time.sleep(0.4)

    ok = rec.is_dir() and not has_config
    print("[PASS] 便携性检查通过" if ok else "[FAIL] 便携性检查未通过")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
