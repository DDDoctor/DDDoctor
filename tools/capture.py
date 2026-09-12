"""把本程序窗口切到前台并抓取整个桌面，用于开发期视觉验证。

    .venv\\Scripts\\python.exe tools\\capture.py --out build_cache\\shot.png

自动查找可见的、属于 python/pythonw 进程的顶层窗口（即本程序主窗口）。
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_uint,
]

HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040
SW_MAXIMIZE = 3


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 2)
    user32.GetWindowTextW(hwnd, buf, length + 2)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def process_name(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


def find_candidates() -> list[tuple[int, str, int]]:
    found: list[tuple[int, str, int]] = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(hwnd)
        if not title:
            return True
        exe = process_name(window_pid(hwnd))
        if exe.startswith("python") or exe.startswith("multiview"):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            found.append((hwnd, title, area))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build_cache/shot.png")
    ap.add_argument("--title", default="", help="标题关键字（可选）")
    ap.add_argument("--min-area", type=int, default=200_000)
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--keep-topmost", action="store_true")
    ap.add_argument("--no-maximize", action="store_true")
    args = ap.parse_args()

    candidates = [c for c in find_candidates() if c[2] >= args.min_area]
    if args.title:
        candidates = [c for c in candidates if args.title in c[1]]
    if not candidates:
        print("没有找到本程序的主窗口")
        return 1

    hwnd, title, area = max(candidates, key=lambda c: c[2])
    print(f"窗口: hwnd={hwnd} area={area} title={title!r}")

    if not args.no_maximize:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
    # SetForegroundWindow 常被系统拒绝，置顶最可靠
    user32.SetWindowPos(
        hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    )
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(args.delay)

    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv[:1])
    screen = QGuiApplication.primaryScreen()
    shot = screen.grabWindow(0)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    shot.save(str(target))
    print(f"已保存 {target}  ({target.stat().st_size} 字节)")

    if not args.keep_topmost:
        user32.SetWindowPos(
            hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
        )
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
