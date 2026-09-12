"""探测本程序主窗口的 UI 线程是否被卡住。

原理：Windows 的 SendMessageTimeoutW(WM_NULL, SMTO_ABORTIFHUNG) 能检测目标窗口的
消息循环是否在超时时间内响应。超时即说明 UI 线程被阻塞。

    .venv\\Scripts\\python.exe tools\\hang_probe.py --seconds 60
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
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM

WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002


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
    handle = kernel32.OpenProcess(0x1000, False, pid)
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


def find_window(pid: int | None = None, title_part: str = "") -> tuple[int, str] | None:
    found: list[tuple[int, str, int]] = []

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(hwnd)
        if not title:
            return True
        wpid = window_pid(hwnd)
        exe = process_name(wpid)
        if not (exe.startswith("python") or exe.startswith("multiview")):
            return True
        if pid is not None and wpid != pid:
            return True
        if title_part and title_part not in title:
            return True
        if pid is None and title_part == "" and "视频墙" not in title and "MultiView" not in title:
            return True
        found.append((hwnd, f"{title}  [pid={wpid}]", wpid))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    if not found:
        return None
    hwnd, title, _ = found[0]
    return hwnd, title


def list_windows() -> list[tuple[int, str, int]]:
    found: list[tuple[int, str, int]] = []

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(hwnd)
        if not title:
            return True
        wpid = window_pid(hwnd)
        exe = process_name(wpid)
        if exe.startswith("python") or exe.startswith("multiview"):
            found.append((hwnd, title, wpid))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def ping(hwnd: int, timeout_ms: int = 800) -> float:
    """返回响应耗时（毫秒）；超时返回 -1。"""
    result = ctypes.c_size_t(0)
    start = time.perf_counter()
    ok = user32.SendMessageTimeoutW(
        hwnd, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result)
    )
    elapsed = (time.perf_counter() - start) * 1000
    return elapsed if ok else -1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--timeout", type=int, default=800)
    ap.add_argument("--wait-window", type=float, default=0.0, help="最多等待窗口出现多少秒")
    ap.add_argument("--pid", type=int, default=None, help="只监视指定进程的窗口")
    ap.add_argument("--list", action="store_true", help="列出所有候选窗口后退出")
    args = ap.parse_args()

    if args.list:
        for hwnd, title, wpid in list_windows():
            print(f"  hwnd={hwnd} pid={wpid}  {title!r}")
        return 0

    target = None
    wait_until = time.time() + args.wait_window
    while target is None:
        target = find_window(args.pid)
        if target is None:
            if time.time() >= wait_until:
                print("未找到主窗口")
                return 1
            time.sleep(0.5)

    hwnd, title = target
    print(f"监视窗口 hwnd={hwnd} title={title!r}")

    end = time.time() + args.seconds
    worst = 0.0
    hung = 0
    samples = 0
    while time.time() < end:
        cost = ping(hwnd, args.timeout)
        samples += 1
        if cost < 0:
            hung += 1
            worst = float(args.timeout)
            print(f"  [{time.strftime('%H:%M:%S')}] 卡住 >{args.timeout}ms")
        else:
            worst = max(worst, cost)
            if cost > 200:
                print(f"  [{time.strftime('%H:%M:%S')}] 响应偏慢 {cost:.0f}ms")
        time.sleep(1.0)

    print()
    print(f"采样 {samples} 次，卡住 {hung} 次，最慢响应 {worst:.0f}ms")
    print("结论：" + ("UI 线程存在明显阻塞！" if hung or worst > 500 else "UI 线程响应正常"))
    return 0 if not hung and worst <= 500 else 2


if __name__ == "__main__":
    sys.exit(main())
