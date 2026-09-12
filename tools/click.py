"""在程序窗口内模拟真实鼠标点击（用于验证双击全屏等交互）。

    .venv\\Scripts\\python.exe tools\\click.py --rel 0.17,0.25 --double
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.hang_probe import (  # noqa: E402
    EnumWindowsProc,
    find_window,
    list_windows,
    user32,
)

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_ulong,
]
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rel", default="0.5,0.5", help="相对窗口的坐标，如 0.17,0.25")
    ap.add_argument("--double", action="store_true")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for hwnd, title, pid in list_windows():
            print(f"  hwnd={hwnd} pid={pid} {title!r}")
        return 0

    # venv 里的 pythonw.exe 是个转发器，窗口属于它的子进程，PID 可能对不上，
    # 所以按 PID 找不到时退回按标题匹配。
    target = find_window(args.pid) if args.pid else find_window()
    if target is None and args.pid:
        target = find_window()
    if target is None:
        print("未找到窗口")
        return 1
    hwnd, title = target
    print(f"目标窗口: {title}")

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    fx, fy = (float(v) for v in args.rel.split(","))
    x = int(rect.left + w * fx)
    y = int(rect.top + h * fy)

    user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    )
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

    user32.SetCursorPos(x, y)
    time.sleep(0.2)

    clicks = 2 if args.double else 1
    for i in range(clicks):
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if i == 0 and clicks == 2:
            time.sleep(0.05)
    print(f"已在窗口 ({w}x{h}) 的 {fx:.2f},{fy:.2f} = ({x},{y}) 点击 {clicks} 次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
