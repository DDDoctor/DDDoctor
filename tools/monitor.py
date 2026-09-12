"""持续监控本程序：卡死瞬间自动抓线程堆栈 + 现场信息。

    .venv\\Scripts\\python.exe tools\\monitor.py --duration 900

每秒采样：
    响应时间（Windows 消息往返）、进程 CPU、进程内存、系统可用内存、系统 CPU
一旦响应超过阈值（默认 1.2s），自动：
    py-spy dump 抓取所有线程的 Python 堆栈、截图、附上程序日志尾部
全部结果写入 monitor_report.txt
"""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.hang_probe import (  # noqa: E402
    find_window,
    list_windows,
    ping,
    user32,
)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


TH32CS_SNAPTHREAD = 0x00000004
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def thread_count(pid: int) -> int:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return -1
    try:
        entry = _THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        n = 0
        ok = kernel32.Thread32First(snap, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                n += 1
            ok = kernel32.Thread32Next(snap, ctypes.byref(entry))
        return n
    finally:
        kernel32.CloseHandle(snap)


def _ft(v: _FILETIME) -> int:
    return (v.dwHighDateTime << 32) | v.dwLowDateTime


def system_memory() -> tuple[float, float]:
    st = _MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(st)
    if kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return st.ullTotalPhys / 2**30, st.ullAvailPhys / 2**30
    return 0.0, 0.0


def system_cpu_times() -> tuple[int, int]:
    idle, kern, user = _FILETIME(), _FILETIME(), _FILETIME()
    if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return _ft(idle), _ft(kern) + _ft(user)
    return 0, 0


def process_cpu_seconds(pid: int) -> float:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return -1.0
    try:
        c, e, k, u = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
        if kernel32.GetProcessTimes(
            h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)
        ):
            return (_ft(k) + _ft(u)) / 1e7
    finally:
        kernel32.CloseHandle(h)
    return -1.0


def process_memory_mb(pid: int) -> float:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return -1.0
    try:
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(h, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / 2**20
    finally:
        kernel32.CloseHandle(h)
    return -1.0


def pyspy_dump(pid: int) -> str:
    exe = ROOT / ".venv" / "Scripts" / "py-spy.exe"
    if not exe.is_file():
        return "(未找到 py-spy)"
    for extra in (["--nonblocking"], []):
        try:
            p = subprocess.run(
                [str(exe), "dump", "--pid", str(pid), *extra],
                capture_output=True,
                text=True,
                timeout=25,
            )
            out = (p.stdout or "") + (p.stderr or "")
            if p.returncode == 0 and out.strip():
                return out
        except Exception as exc:  # noqa: BLE001
            out = f"(py-spy 失败: {exc})"
    return out or "(py-spy 无输出)"


def screenshot(tag: str) -> str:
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication(sys.argv[:1])
        screen = QGuiApplication.primaryScreen()
        target = ROOT / "build_cache" / f"hang_{tag}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        screen.grabWindow(0).save(str(target))
        del app
        return str(target)
    except Exception as exc:  # noqa: BLE001
        return f"(截图失败: {exc})"


def log_tail(n: int = 25) -> str:
    for cand in (ROOT / "dist" / "MultiView" / "multiview.log", ROOT / "multiview.log"):
        if cand.is_file():
            try:
                lines = cand.read_text(encoding="utf-8", errors="replace").splitlines()
                return f"--- {cand} (最后 {n} 行) ---\n" + "\n".join(lines[-n:])
            except Exception:  # noqa: BLE001
                pass
    return "(未找到 multiview.log)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=900)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--threshold", type=float, default=1.2, help="判定卡死的响应阈值（秒）")
    ap.add_argument("--out", default=str(ROOT / "monitor_report.txt"))
    ap.add_argument("--no-pyspy", action="store_true")
    args = ap.parse_args()

    report = Path(args.out)
    report.parent.mkdir(parents=True, exist_ok=True)
    fh = open(report, "w", encoding="utf-8", buffering=1)

    def emit(line: str) -> None:
        print(line, flush=True)
        fh.write(line + "\n")

    emit(f"# 监控开始 {time.strftime('%Y-%m-%d %H:%M:%S')}  时长 {args.duration:.0f}s  阈值 {args.threshold}s")
    emit("# 时间     响应     进程CPU   进程内存   线程   系统内存        系统CPU")

    end = time.time() + args.duration
    last_pid = None
    last_cpu = None
    last_t = None
    idle0, total0 = system_cpu_times()
    t_cpu0 = time.time()
    hang_active = False
    hang_count = 0
    hang_samples = 0
    total_cpu_in_hang = 0.0
    last_dump_t = 0.0

    while time.time() < end:
        target = find_window()
        if target is None:
            if last_pid is not None:
                emit(f"[{time.strftime('%H:%M:%S')}] 窗口消失（程序退出或已关闭）")
                last_pid = None
                last_cpu = None
                hang_active = False
            time.sleep(args.interval)
            continue

        hwnd, title = target
        pid = None
        for h, _t, p in list_windows():
            if h == hwnd:
                pid = p
                break
        if pid is None:
            time.sleep(args.interval)
            continue

        if pid != last_pid:
            emit(f"[{time.strftime('%H:%M:%S')}] 开始监视 pid={pid}  {title}")
            last_pid = pid
            last_cpu = process_cpu_seconds(pid)
            last_t = time.time()

        resp = ping(hwnd, int(args.threshold * 1000))

        now = time.time()
        cpu = process_cpu_seconds(pid)
        cores = (cpu - last_cpu) / max(now - last_t, 1e-6) if (last_cpu and cpu >= 0) else 0.0
        last_cpu, last_t = cpu, now

        ws = process_memory_mb(pid)
        threads = thread_count(pid)
        total_gb, avail_gb = system_memory()

        idle1, total1 = system_cpu_times()
        syscpu = 1.0 - (idle1 - idle0) / max(total1 - total0, 1)
        idle0, total0 = idle1, total1

        resp_txt = f"{resp:6.0f}ms" if resp >= 0 else "  卡死!"
        line = (
            f"[{time.strftime('%H:%M:%S')}] {resp_txt}  "
            f"{cores * 100:6.0f}%  {ws / 1024:6.2f}GB  {threads:4d}  "
            f"{avail_gb:5.2f}/{total_gb:.1f}GB  {syscpu * 100:5.0f}%"
        )
        emit(line)

        if resp < 0:
            hang_count += 1
            hang_samples += 1
            total_cpu_in_hang += cores
            if not hang_active:
                hang_active = True
                emit("")
                emit("=" * 78)
                emit(f"!!! 检测到卡死 {time.strftime('%H:%M:%S')}  窗口标题: {title}")
                emit(f"    进程内存 {ws / 1024:.2f} GB   系统可用内存 {avail_gb:.2f} GB")
                if not args.no_pyspy and now - last_dump_t > 10:
                    last_dump_t = now
                    emit("--- 线程堆栈 (py-spy dump) ---")
                    emit(pyspy_dump(pid))
                shot = screenshot(time.strftime("%H%M%S"))
                emit(f"--- 现场截图: {shot} ---")
                emit(log_tail())
                emit("=" * 78)
                emit("")
        else:
            if hang_active:
                emit("")
                emit(
                    f">>> 已恢复 {time.strftime('%H:%M:%S')}  "
                    f"本次卡死持续 {hang_samples} 秒，期间平均占用 {total_cpu_in_hang / max(hang_samples, 1) * 100:.0f}%"
                )
                emit("")
                hang_active = False
                hang_samples = 0
                total_cpu_in_hang = 0.0

        time.sleep(args.interval)

    emit("")
    emit(f"# 监控结束 {time.strftime('%Y-%m-%d %H:%M:%S')}  共检测到卡死采样 {hang_count} 次")
    fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
