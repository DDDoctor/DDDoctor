"""验证双击事件的触发次数与放大/全屏行为。

    .venv\\Scripts\\python.exe tools\\dblclick_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

vlc_runtime.prepare()

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.cell import VideoCell  # noqa: E402
from app.config import AppConfig  # noqa: E402
from app.main_window import MainWindow  # noqa: E402

app = QApplication(sys.argv)

# ---------------------------------------------------------------- 1. 单元格 ----
cell = VideoCell(0, "测试通道")
cell.resize(400, 300)
cell.show()
app.processEvents()

hits: list[int] = []
cell.clicked.connect(lambda i: hits.append(("click", i)))
cell.doubleClicked.connect(lambda i: hits.append(("dblclick", i)))


def synth(widget, kind) -> None:
    ev = QMouseEvent(
        kind,
        QPointF(20.0, 20.0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, ev)


hits.clear()
synth(cell.video_widget(), QEvent.Type.MouseButtonDblClick)
print(f"[1] 双击画面区 -> doubleClicked 触发 {len([h for h in hits if h[0] == 'dblclick'])} 次  {hits}")
print("    期望 1 次；若为 2 次说明事件冒泡到父控件被重复处理")

hits.clear()
synth(cell.video_widget(), QEvent.Type.MouseButtonPress)
print(f"[2] 单击画面区 -> clicked 触发 {len([h for h in hits if h[0] == 'click'])} 次  {hits}")

hits.clear()
synth(cell.header, QEvent.Type.MouseButtonDblClick)
print(f"[3] 双击标题栏 -> doubleClicked 触发 {len([h for h in hits if h[0] == 'dblclick'])} 次")

# ---------------------------------------------------------------- 2. 主窗口 ----
cfg = AppConfig()
for i in range(4):
    ch = cfg.channels[i]
    ch.enabled = True
    ch.name = f"通道{i + 1}"
    ch.url = f"rtsp://192.0.2.1:554/{i}"
    ch.muted = True
cfg.autoplay_on_start = False
cfg.normalize()

window = MainWindow(cfg)
window.resize(1280, 800)
window.show()
app.processEvents()

calls: list[int] = []
orig = window._on_cell_double_clicked  # noqa: SLF001


def spy(index: int) -> None:
    calls.append(index)
    orig(index)


window._on_cell_double_clicked = spy  # type: ignore[method-assign]
window.wall.cellDoubleClicked.disconnect()
window.wall.cellDoubleClicked.connect(spy)

print()
print("[4] 主窗口：模拟一次双击通道1的画面")
before = window._zoom  # noqa: SLF001
synth(window.wall.cell(0).video_widget(), QEvent.Type.MouseButtonDblClick)
app.processEvents()
print(f"    处理器被调用 {len(calls)} 次，_zoom: {before} -> {window._zoom}")  # noqa: SLF001
print(f"    是否全屏: {window.isFullScreen()}   菜单栏可见: {window.menuBar().isVisible()}")
if window.wall.cell(0):
    print(f"    通道1 是否铺满: {window.wall.cell(0).isVisible()}  "
          f"通道2 是否隐藏: {not window.wall.cell(1).isVisible()}")

print()
print("[5] 再模拟一次双击（应还原）")
synth(window.wall.cell(0).video_widget(), QEvent.Type.MouseButtonDblClick)
app.processEvents()
print(f"    _zoom={window._zoom}  全屏={window.isFullScreen()}  菜单栏可见={window.menuBar().isVisible()}")

window.close()
app.processEvents()
sys.exit(0)
