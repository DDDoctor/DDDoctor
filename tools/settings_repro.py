"""复现「配置 → 确定」导致的 UI 卡死，并验证修复效果。

v1.0.2 及更早：主线程在 _rebuild_wall() 里调用 video_set_aspect_ratio()，
而该方法要抢 libvlc 的 input 锁，被后台正在执行的 stop() 长时间占着，
于是主线程被堵住十几秒。

    .venv\\Scripts\\python.exe tools\\settings_repro.py --n 11
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

DEAD = "rtsp://192.0.2.1:554/Streaming/Channels/1?transportmode=unicast&profile=Profile_1"

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=11)
ap.add_argument("--url", default=DEAD)
ap.add_argument("--wait", type=float, default=8.0)
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
window.setWindowTitle("多通道视频墙 复现测试")
app.processEvents()


def phase_play() -> None:
    print(f"[1] 起 {args.n} 路（{args.url[:48]}…）", flush=True)
    window.play_all()
    print(f"    等待 {args.wait:.0f}s 让各路进入连接/重连…", flush=True)
    QTimer.singleShot(int(args.wait * 1000), phase_settings)


def phase_settings() -> None:
    # 完全复刻 open_settings() 在 engine 未变时走的路径
    print("[2] 模拟「配置 → 确定」：stop_all() + _rebuild_wall()", flush=True)
    t0 = time.perf_counter()
    window.stop_all()
    t_stop = time.perf_counter() - t0

    t0 = time.perf_counter()
    window._rebuild_wall()  # noqa: SLF001
    t_rebuild = time.perf_counter() - t0

    print(f"    stop_all()      : {t_stop * 1000:8.0f} ms", flush=True)
    print(f"    _rebuild_wall() : {t_rebuild * 1000:8.0f} ms   <== 修复前这里是几秒~十几秒", flush=True)

    t0 = time.perf_counter()
    window._rebuild_wall()  # noqa: SLF001
    t_rebuild2 = time.perf_counter() - t0
    print(f"    _rebuild_wall()2: {t_rebuild2 * 1000:8.0f} ms", flush=True)

    worst = max(t_stop, t_rebuild, t_rebuild2)
    print()
    print(f"最慢一步 UI 线程阻塞: {worst * 1000:.0f} ms")
    print("结论：" + ("仍然会卡死！" if worst > 0.5 else "UI 线程没有被阻塞 ✅"))

    window.close()
    # closeEvent 会先隐藏窗口、再在后台收尾并自己退出事件循环
    QTimer.singleShot(4000, app.quit)


QTimer.singleShot(500, phase_play)
app.exec()
