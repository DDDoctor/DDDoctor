"""对照实验：把后台派发改成「同步执行」，模拟 v1.0.0 修复前的行为。

    .venv\\Scripts\\python.exe tools\\old_behavior_app.py

然后用 tools/hang_probe.py 从另一个进程探测，即可看到 UI 被阻塞。
仅用于验证修复效果，不参与打包。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

vlc_runtime.prepare()

import app.dispatch as dispatch_mod  # noqa: E402

# —— 关键：让所有「后台」作业在调用线程（也就是 UI 线程）里同步执行 ——
_SLOW: list[tuple[str, float]] = []


def _sync_post(self, label, fn):  # type: ignore[no-untyped-def]
    import time as _t

    t0 = _t.perf_counter()
    try:
        fn()
    except Exception:  # noqa: BLE001
        pass
    dt = (_t.perf_counter() - t0) * 1000
    if dt > 200:
        _SLOW.append((label, dt))
        with open(ROOT / "old_behavior_slow.txt", "a", encoding="utf-8") as fh:
            fh.write(f"{label}\t{dt:.0f}ms\n")


dispatch_mod.VlcDispatcher.post = _sync_post  # type: ignore[method-assign]

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.paths import config_path  # noqa: E402

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    filename=str(ROOT / "old_behavior.log"),
    filemode="w",
    encoding="utf-8",
)

app = QApplication(sys.argv)
cfg = AppConfig.load(config_path())
window = MainWindow(cfg)
window.show()
sys.exit(app.exec())
