"""给本程序主窗口发送 WM_CLOSE（模拟点关闭按钮）。

    .venv\\Scripts\\python.exe tools\\close_app.py [--pid N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.hang_probe import find_window, list_windows, window_pid, user32  # noqa: E402

WM_CLOSE = 0x0010


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for hwnd, title, pid in list_windows():
            print(f"  hwnd={hwnd} pid={pid} {title!r}")
        return 0

    target = find_window(args.pid) if args.pid else find_window()
    if target is None and args.pid:
        target = find_window()
    if target is None:
        print("未找到窗口")
        return 1

    hwnd, title = target
    pid = window_pid(hwnd)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    print(f"已向 pid={pid} 发送 WM_CLOSE  ({title})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
