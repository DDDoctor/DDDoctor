"""对比硬解/软解的实际 CPU 占用，判断 --avcodec-hw 是否真的生效。

    .venv\\Scripts\\python.exe tools\\hw_probe.py --n 8 --seconds 45
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
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.dispatch import VlcDispatcherPool  # noqa: E402
from app.player import ChannelPlayer, VlcEngine  # noqa: E402

URL = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=8)
ap.add_argument("--seconds", type=float, default=45)
ap.add_argument("--hw", default="any")
args = ap.parse_args()

cfg = AppConfig()
cfg.hw_decode = args.hw
cfg.network_caching = 300
cfg.normalize()

app = QApplication(sys.argv)
engine = VlcEngine(cfg)
pool = VlcDispatcherPool(size=4)

window = QWidget()
window.resize(1280, 720)
window.show()

players = []
for i in range(args.n):
    w = QWidget(window)
    w.resize(320, 180)
    w.move((i % 4) * 320, (i // 4) * 180)
    p = ChannelPlayer(i, engine, pool.for_index(i))
    p.bind_widget(w)
    p.apply_config(0, True, "keep")
    players.append(p)

state = {"cpu0": 0.0, "t0": 0.0}


def start_cpu_sampling() -> None:
    proc = next(
        (
            p
            for p in __import__("psutil").process_iter()
            if p.pid == __import__("os").getpid()
        ),
        None,
    )
    state["cpu0"] = time.process_time()
    state["t0"] = time.monotonic()


def report() -> None:
    wall = time.monotonic() - state["t0"]
    cpu = time.process_time() - state["cpu0"]
    print(f"  hw={args.hw}  {args.n} 路  {wall:.0f}s 内消耗 CPU 时间 {cpu:.1f}s"
          f"  ≈ {cpu / wall * 100:.0f}% 单核")
    for p in players:
        p.destroy()
    pool.shutdown()
    engine.release()
    app.quit()


for p in players:
    p.play(URL)


def begin() -> None:
    state["cpu0"] = time.process_time()
    state["t0"] = time.monotonic()
    QTimer.singleShot(int(args.seconds * 1000), report)


# 先给 15 秒让所有流进入播放
QTimer.singleShot(15000, begin)
QTimer.singleShot(15000 + int(args.seconds * 1000) + 100, report)
app.exec()
