"""逐路检查画面：状态、是否有 vout、绑定的窗口句柄是否还有效。

    .venv\\Scripts\\python.exe tools\\cells_probe.py --n 4
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

HLS = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=4)
ap.add_argument("--url", default=HLS)
ap.add_argument("--wait", type=float, default=35.0)
ap.add_argument("--no-autoplay", action="store_true")
args = ap.parse_args()

cfg = AppConfig()
cfg.autoplay_on_start = False
cfg.connect_timeout = 30
cfg.network_caching = 1000
for i in range(args.n):
    ch = cfg.channels[i]
    ch.enabled = True
    ch.name = f"通道{i + 1}"
    ch.url = args.url
    ch.muted = True
cfg.normalize()

app = QApplication(sys.argv)
window = MainWindow(cfg)
window.resize(1440, 860)
window.show()
window.setWindowTitle("多通道视频墙 画面探测")
app.processEvents()

# 记录绑定时的句柄
bound: dict[int, int] = {}


def remember() -> None:
    for index, cell in window.wall.cells.items():
        bound.setdefault(index, int(cell.video_widget().winId()))


QTimer.singleShot(0, remember)


def phase_play() -> None:
    print(f"[1] 起 {args.n} 路并等待 {args.wait:.0f}s", flush=True)
    remember()
    if not args.no_autoplay:
        window.play_all()
    QTimer.singleShot(int(args.wait * 1000), report)


def report() -> None:
    print()
    print(f"{'通道':<6}{'状态':<12}{'vout':<6}{'画面尺寸':<14}{'绑定句柄':<12}{'当前句柄':<12}判断")
    print("-" * 78)
    black = []
    for index in sorted(window.wall.cells):
        cell = window.wall.cells[index]
        player = window.players[index]
        try:
            has_vout = player._player.has_vout()  # noqa: SLF001
        except Exception:  # noqa: BLE001
            has_vout = -1
        try:
            w, h = player._player.video_get_size(0)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            w = h = -1
        cur = int(cell.video_widget().winId())
        bnd = int(player._widget_id or 0)  # VLC 实际绑定的句柄  # noqa: SLF001
        reasons = []
        if player.state != "playing":
            reasons.append(f"状态={player.state}")
        if not has_vout:
            reasons.append("无视频输出")
        if w in (0, -1) and h in (0, -1):
            reasons.append("画面尺寸未知")
        if bnd != cur:
            reasons.append("VLC 绑定的句柄已失效(窗口被重建)")
        if cell.placeholder.isVisible():
            reasons.append("占位层仍可见")
        flag = "OK" if not reasons else "黑屏: " + ", ".join(reasons)
        if reasons:
            black.append(index + 1)
        print(
            f"{index + 1:<6}{player.state:<12}{str(has_vout):<6}"
            f"{f'{w}x{h}':<14}{str(bnd):<12}{str(cur):<12}{flag}"
        )

    print()
    print(f"黑屏通道: {black if black else '无'}")
    if args.n >= 5:
        rows, cols = window.wall._row_counts if False else (0, 0)  # noqa: SLF001
    print(f"网格: {len(window.wall.cells)} 格")
    window.close()
    QTimer.singleShot(3000, app.quit)


QTimer.singleShot(400, phase_play)
app.exec()
