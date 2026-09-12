"""测量 libvlc 阻塞调用在 UI 线程上的耗时 —— 定位「多通道卡死」。

    .venv\\Scripts\\python.exe tools\\block_probe.py [--url URL] [--n 8]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

vlc_runtime.prepare()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

DEAD = "rtsp://192.0.2.1:554/Streaming/Channels/101?transportmode=unicast&profile=Profile_1"

ap = argparse.ArgumentParser()
ap.add_argument("--url", default=DEAD)
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--wait", type=float, default=6.0, help="起流后等多久再测 stop")
args = ap.parse_args()

cfg = AppConfig()
cfg.autoplay_on_start = False
cfg.connect_timeout = 15
for i in range(args.n):
    ch = cfg.channels[i]
    ch.enabled = True
    ch.name = f"通道{i + 1}"
    ch.url = args.url
    ch.muted = True
cfg.normalize()

app = QApplication(sys.argv)
window = MainWindow(cfg)
window.show()
window.setWindowTitle("多通道视频墙 v1.0.0")
app.processEvents()

results: dict[str, float] = {}


def timed(label: str, fn) -> float:
    t0 = time.perf_counter()
    fn()
    dt = time.perf_counter() - t0
    results[label] = dt
    print(f"  {label}: {dt * 1000:.0f} ms", flush=True)
    return dt


def phase_play() -> None:
    print(f"[1] play_all()（{args.n} 路）", flush=True)
    timed("play_all", window.play_all)
    print(f"    等待 {args.wait}s 让各路进入连接/缓冲…", flush=True)
    QTimer.singleShot(int(args.wait * 1000), phase_stop)


def phase_stop() -> None:
    print("[2] stop_all()（此时各路仍在连接中）", flush=True)
    worst = timed("stop_all", window.stop_all)

    print("[3] 逐路 stop() 单独计时", flush=True)
    window.play_all()
    QTimer.singleShot(3000, phase_individual)
    results["stop_all#"] = worst


def phase_individual() -> None:
    times = []
    for idx in sorted(window.wall.cells):
        player = window.players[idx]
        t0 = time.perf_counter()
        player.stop()
        dt = (time.perf_counter() - t0) * 1000
        times.append((idx + 1, dt))
    for idx, dt in times:
        flag = "  <== 阻塞!" if dt > 200 else ""
        print(f"    通道 {idx:02d} stop(): {dt:.0f} ms{flag}", flush=True)

    print("[4] 二次 stop_all()（已停止状态）", flush=True)
    timed("stop_all_again", window.stop_all)

    print("[5] destroy 全部播放器", flush=True)
    timed("destroy_players", window._destroy_players)  # noqa: SLF001
    app.quit()


QTimer.singleShot(500, phase_play)
app.exec()

print()
worst = max(v for k, v in results.items() if k != "stop_all#")
print(f"最慢单次阻塞调用: {worst * 1000:.0f} ms")
print("结论：" + ("存在明显 UI 阻塞风险！" if worst > 0.3 else "未发现秒级阻塞"))
sys.exit(2 if worst > 0.3 else 0)
