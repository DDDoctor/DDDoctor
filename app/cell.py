"""单个通道画面单元：标题栏 + 视频画面区 + 状态占位层。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .constants import (
    HEADER_HEIGHT,
    STATE_COLOR,
    STATE_IDLE,
    STATE_PLAYING,
    STATE_TEXT,
)

_ACCENT = "#2d8cf0"


class _VideoSurface(QWidget):
    """VLC 视频输出目标窗口。"""

    def __init__(self, cell: "VideoCell") -> None:
        super().__init__(cell)
        self._cell = cell
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#000000"))
        self.setPalette(pal)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(32, 24)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._cell.sync_placeholder()

    # VLC 可能吞掉鼠标事件，这里的处理只是「尽力而为」，
    # 真正可靠的交互入口是标题栏和工具栏。
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._cell.notify_clicked()
        super().mousePressEvent(event)
        # QWidget 默认会 ignore() 掉鼠标事件，事件就会继续冒泡到父控件
        # （VideoCell）再被处理一次 —— 双击因此变成「放大后又立刻还原」。
        # 这里显式 accept，阻断冒泡。
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._cell.notify_double_clicked()
        super().mouseDoubleClickEvent(event)
        event.accept()


class _Placeholder(QLabel):
    """未播放 / 异常时覆盖在画面上的提示层（原生窗口才能盖住 VLC 的输出窗口）。"""

    def __init__(self, cell: "VideoCell") -> None:
        super().__init__(cell)
        self._cell = cell
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "background-color:#101216; color:#8b93a1; font-size:13px; padding:6px;"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._cell.notify_clicked()
        super().mousePressEvent(event)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._cell.notify_double_clicked()
        super().mouseDoubleClickEvent(event)
        event.accept()


class VideoCell(QFrame):
    """一个通道的画面单元。"""

    clicked = Signal(int)
    doubleClicked = Signal(int)
    #: (通道序号, 画面宽, 画面高) —— 画面区尺寸变化，用于「拉伸铺满」
    resized = Signal(int, int, int)

    def __init__(self, index: int, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self._state = STATE_IDLE
        self._detail = ""
        self._selected = False
        self._header_visible = True
        self._recording = False
        self._qss = ""

        self.setObjectName("VideoCell")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumSize(80, 60)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- 标题栏 ---------------------------------------------------- #
        self.header = QWidget(self)
        self.header.setFixedHeight(HEADER_HEIGHT)
        self.header.setStyleSheet("background-color:#1b1f27;")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(8, 0, 8, 0)
        hl.setSpacing(6)

        self.name_label = QLabel(title, self.header)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        self.name_label.setFont(f)
        self.name_label.setStyleSheet("color:#e6e9ef; background:transparent;")

        self.badge_label = QLabel("", self.header)
        self.badge_label.setStyleSheet("color:#ffb454; background:transparent; font-size:11px;")

        #: 声音状态角标：🔊 出声 / 🔇 静音
        self.audio_label = QLabel("", self.header)
        self.audio_label.setStyleSheet(
            "color:#5c6472; background:transparent; font-size:11px;"
        )

        self.status_label = QLabel("", self.header)
        self.status_label.setStyleSheet("color:#9aa4b2; background:transparent; font-size:11px;")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        hl.addWidget(self.name_label, 0)
        hl.addWidget(self.audio_label, 0)
        hl.addWidget(self.badge_label, 0)
        hl.addStretch(1)
        hl.addWidget(self.status_label, 0)

        # --- 画面区 ---------------------------------------------------- #
        self.video = _VideoSurface(self)

        self.placeholder = _Placeholder(self)
        self.placeholder.setText("未播放")

        root.addWidget(self.header, 0)
        root.addWidget(self.video, 1)

        self._apply_style()

    # ------------------------------------------------------------------ #

    def video_widget(self) -> QWidget:
        return self.video

    def notify_clicked(self) -> None:
        self.clicked.emit(self.index)

    def notify_double_clicked(self) -> None:
        self.doubleClicked.emit(self.index)

    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.notify_clicked()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.notify_double_clicked()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.sync_placeholder()

    def sync_placeholder(self) -> None:
        top_left = self.video.mapTo(self, self.video.rect().topLeft())
        self.placeholder.setGeometry(
            top_left.x(), top_left.y(), self.video.width(), self.video.height()
        )
        if self.placeholder.isVisible():
            self.placeholder.raise_()
        self.resized.emit(self.index, self.video.width(), self.video.height())

    # ------------------------------------------------------------------ #

    def set_title(self, title: str) -> None:
        self.name_label.setText(title)

    def set_header_visible(self, visible: bool) -> None:
        self._header_visible = bool(visible)
        self.header.setVisible(self._header_visible)
        self.sync_placeholder()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = bool(selected)
        self._apply_style()

    def set_recording(self, recording: bool) -> None:
        self._recording = bool(recording)
        self.badge_label.setText("● REC" if self._recording else "")
        self._apply_style()

    def set_mute_hint(self, muted: bool, volume: int) -> None:
        self.setToolTip(
            f"通道 {self.index + 1} · {'静音' if muted else f'音量 {volume}%'}"
        )
        self.audio_label.setText("🔇" if muted else "🔊")
        self.audio_label.setStyleSheet(
            "color:#5c6472; background:transparent; font-size:11px;"
            if muted
            else "color:#2ecc71; background:transparent; font-size:11px;"
        )

    def set_state(self, state: str, detail: str) -> None:
        if state == self._state and detail == self._detail:
            return
        self._state = state
        self._detail = detail
        text = STATE_TEXT.get(state, state)
        self.status_label.setText(f"{text}{(' · ' + detail) if detail else ''}")

        playing = state == STATE_PLAYING
        self.placeholder.setVisible(not playing)
        if not playing:
            lines = [self.name_label.text(), text]
            if detail:
                lines.append(detail)
            body = "\n".join(lines)
            if self.placeholder.text() != body:
                self.placeholder.setText(body)
            self.placeholder.raise_()
        self._apply_style()

    # ------------------------------------------------------------------ #

    def _apply_style(self) -> None:
        color = STATE_COLOR.get(self._state, "#4a4a4a")
        width = 2 if self._selected else 1
        if self._selected:
            color = _ACCENT if self._state == STATE_IDLE else color
        # setStyleSheet 会触发整个子控件树的样式重算，18 路高频状态变化时
        # 必须做缓存，否则界面会被拖垮
        qss = f"#VideoCell {{ background-color:#000000; border:{width}px solid {color}; }}"
        if qss != self._qss:
            self._qss = qss
            self.setStyleSheet(qss)
        if self.header.isVisible() != self._header_visible:
            self.header.setVisible(self._header_visible)
