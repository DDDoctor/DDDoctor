"""程序入口。

注意：必须先调用 :func:`app.vlc_runtime.prepare` 把内置 VLC 目录接入 DLL 搜索路径，
之后才能 ``import vlc``（app.player 会导入它）。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def _setup_logging() -> None:
    from app.paths import log_path

    handlers: list[logging.Handler] = []
    try:
        handlers.append(
            RotatingFileHandler(
                log_path(), maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
            )
        )
    except Exception:  # noqa: BLE001
        pass
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers or None,
    )
    logging.getLogger("vlc").setLevel(logging.WARNING)


_DARK_QSS = """
QWidget { background-color:#12151a; color:#d7dce5; font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif; font-size:12px; }
QMainWindow, QDialog { background-color:#12151a; }
QToolBar { background-color:#1b1f27; border:0; spacing:4px; padding:4px; }
QToolBar QLabel { color:#8b93a1; }
QPushButton { background-color:#242a35; border:1px solid #333c4a; border-radius:4px; padding:4px 10px; color:#d7dce5; }
QPushButton:hover { background-color:#2d3644; border-color:#3d4a5c; }
QPushButton:pressed { background-color:#1d232c; }
QPushButton:checked { background-color:#2d8cf0; border-color:#2d8cf0; color:#ffffff; }
QPushButton:disabled { color:#5c6472; background-color:#1a1e25; }
QComboBox { background-color:#242a35; border:1px solid #333c4a; border-radius:4px; padding:3px 6px; }
QComboBox QAbstractItemView { background-color:#1b1f27; selection-background-color:#2d8cf0; }
QLineEdit, QSpinBox, QPlainTextEdit { background-color:#1b1f27; border:1px solid #333c4a; border-radius:4px; padding:3px 6px; }
QTableWidget { background-color:#161a20; gridline-color:#262d38; border:1px solid #262d38; }
QHeaderView::section { background-color:#1b1f27; border:0; border-right:1px solid #262d38; padding:4px 6px; color:#9aa4b2; }
QTabWidget::pane { border:1px solid #262d38; }
QTabBar::tab { background-color:#1b1f27; padding:6px 14px; border:1px solid #262d38; border-bottom:0; }
QTabBar::tab:selected { background-color:#242a35; color:#ffffff; }
QGroupBox { border:1px solid #262d38; border-radius:4px; margin-top:8px; }
QMenuBar { background-color:#1b1f27; }
QMenuBar::item:selected { background-color:#2d3644; }
QMenu { background-color:#1b1f27; border:1px solid #333c4a; }
QMenu::item:selected { background-color:#2d8cf0; }
QStatusBar { background-color:#1b1f27; color:#9aa4b2; }
QCheckBox { spacing:6px; }
QScrollBar:vertical { background:#161a20; width:10px; }
QScrollBar::handle:vertical { background:#39414f; border-radius:5px; min-height:24px; }
QScrollBar:horizontal { background:#161a20; height:10px; }
QScrollBar::handle:horizontal { background:#39414f; border-radius:5px; min-width:24px; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; width:0; }
"""


def main() -> int:
    import time

    t0 = time.perf_counter()

    def boot(msg: str) -> None:
        logging.getLogger("app.boot").info("%s  (+%.2fs)", msg, time.perf_counter() - t0)

    # 1) 先接好 VLC 运行库（必须在 import vlc 之前）
    _setup_logging()
    boot("程序启动")

    from app import vlc_runtime

    vlc_dir = vlc_runtime.prepare()
    boot(f"VLC 运行库就绪: {vlc_dir}")

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
    app = QApplication(sys.argv)
    app.setApplicationName("MultiView")
    app.setStyleSheet(_DARK_QSS)

    if vlc_dir is None:
        QMessageBox.critical(
            None,
            "缺少 VLC 运行库",
            "未找到 libvlc.dll / libvlccore.dll。\n\n"
            "请确认程序目录下的 vlc 文件夹完整；\n"
            "或安装 64 位 VLC 播放器（https://www.videolan.org/）；\n"
            "也可以通过环境变量 MULTIVIEW_VLC_DIR 指定 VLC 运行库目录。",
        )
        return 2

    from app.config import AppConfig, demo_config
    from app.main_window import MainWindow
    from app.paths import config_path

    if config_path().is_file():
        config = AppConfig.load(config_path())
    else:
        config = demo_config()
        try:
            config.save(config_path())
        except Exception:  # noqa: BLE001
            pass

    window = MainWindow(config)
    boot("主窗口构建完成")
    window.show()
    boot("进入事件循环")
    return app.exec()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
