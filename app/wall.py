"""自动网格布局：根据通道数量与窗口比例计算并摆放画面单元。

布局目标：让每个单元格的宽高比尽量接近 16:9（摄像头/视频流的常见比例），
同时尽量减少空白单元格带来的浪费。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .cell import VideoCell

#: 假定的视频画面宽高比
VIDEO_ASPECT = 16.0 / 9.0


def _waste(rows: int, counts: Sequence[int], screen_aspect: float) -> float:
    """估算该布局下「黑边 + 空格」占窗口面积的比例（越小越好）。"""
    total = 0.0
    for count in counts:
        if count <= 0:
            continue
        cell_w = 1.0 / count
        cell_h = 1.0 / rows
        cell_aspect = (cell_w * screen_aspect) / cell_h
        used = min(cell_aspect, VIDEO_ASPECT) / max(cell_aspect, VIDEO_ASPECT)
        area = cell_w * cell_h
        total += (1.0 - used) * area * count
    # 未填满的格子本身就是纯黑
    empty = rows * max(counts) - sum(counts) if counts else 0
    if empty > 0:
        total += empty * (1.0 / max(counts)) * (1.0 / rows)
    return total


def compute_grid(
    n: int,
    screen_aspect: float = 16.0 / 9.0,
    fill_last_row: bool = False,
) -> Tuple[int, int]:
    """返回 (行数, 列数)。"""
    if n <= 0:
        return 0, 0
    if n == 1:
        return 1, 1

    best: Optional[Tuple[float, int, int]] = None
    for rows in range(1, n + 1):
        cols = math.ceil(n / rows)
        if rows * cols > 36:
            continue
        if fill_last_row:
            counts = _row_counts(n, rows, cols)
            cost = _waste(rows, counts, screen_aspect)
        else:
            cost = _waste(rows, [cols] * rows, screen_aspect)
        key = (round(cost, 6), rows)
        if best is None or key < (best[0], best[1]):
            best = (cost, rows, cols)
    assert best is not None
    return best[1], best[2]


def _row_counts(n: int, rows: int, cols: int) -> List[int]:
    """把 n 个单元分配到 rows 行，前面的行优先放满。"""
    counts: List[int] = []
    left = n
    for _ in range(rows):
        take = min(cols, left)
        counts.append(take)
        left -= take
    return counts


class VideoWall(QWidget):
    """按自动网格摆放 VideoCell 的容器。"""

    cellClicked = Signal(int)
    cellDoubleClicked = Signal(int)
    #: (通道序号, 画面宽, 画面高)
    cellResized = Signal(int, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(1)
        self._cells: Dict[int, VideoCell] = {}
        self._rows: List[QWidget] = []
        self._indices: List[int] = []
        self._zoom: Optional[int] = None
        self._header_visible = True
        self._fill_last_row = False
        self._empty = QWidget(self)
        self._empty.setStyleSheet("background-color:#0b0d10;")
        self._root.addWidget(self._empty, 1)

    # ------------------------------------------------------------------ #

    @property
    def cells(self) -> Dict[int, VideoCell]:
        return self._cells

    @property
    def indices(self) -> List[int]:
        return list(self._indices)

    @property
    def zoom_index(self) -> Optional[int]:
        return self._zoom

    def cell(self, index: int) -> Optional[VideoCell]:
        return self._cells.get(index)

    # ------------------------------------------------------------------ #

    def rebuild(
        self,
        entries: Sequence[Tuple[int, str]],
        fill_last_row: bool = False,
        screen_aspect: float = VIDEO_ASPECT,
    ) -> None:
        """按 (通道序号, 标题) 列表重建网格；播放器对象由外部维护，不会被销毁。"""
        self._indices = [idx for idx, _ in entries]
        self._fill_last_row = fill_last_row
        self._zoom = None

        # 清空旧布局（只解除父子关系，不销毁 widget）
        self._teardown()

        if not entries:
            self._empty = QWidget(self)
            self._empty.setStyleSheet("background-color:#0b0d10;")
            self._root.addWidget(self._empty, 1)
            self._cells = {}
            return

        if not (0.2 <= screen_aspect <= 8.0):
            screen_aspect = VIDEO_ASPECT
        rows, cols = compute_grid(len(entries), screen_aspect, fill_last_row)

        self._cells = {}
        pos = 0
        for r in range(rows):
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(1)

            count = min(cols, len(entries) - pos)
            for _ in range(count):
                idx, title = entries[pos]
                cell = VideoCell(idx, title, row_widget)
                cell.clicked.connect(self.cellClicked)
                cell.doubleClicked.connect(self.cellDoubleClicked)
                cell.resized.connect(self.cellResized)
                cell.set_header_visible(self._header_visible)
                row_layout.addWidget(cell, 1)
                self._cells[idx] = cell
                pos += 1
            row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self._root.addWidget(row_widget, 1)
            self._rows.append(row_widget)

        self._root.setStretchFactor(self._rows[0] if self._rows else self._empty, 1)

    def _teardown(self) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        if self._empty is not None:
            self._root.removeWidget(self._empty)
            self._empty.setParent(None)
            self._empty.deleteLater()
            self._empty = None  # type: ignore[assignment]
        # 移除所有布局项
        while self._root.count():
            item = self._root.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._cells = {}

    # ------------------------------------------------------------------ #

    def set_header_visible(self, visible: bool) -> None:
        self._header_visible = bool(visible)
        for cell in self._cells.values():
            cell.set_header_visible(self._header_visible)

    def set_selected(self, index: Optional[int]) -> None:
        for idx, cell in self._cells.items():
            cell.set_selected(idx == index)

    def update_cell_state(self, index: int, state: str, detail: str) -> None:
        cell = self._cells.get(index)
        if cell is not None:
            cell.set_state(state, detail)

    def update_cell_title(self, index: int, title: str) -> None:
        cell = self._cells.get(index)
        if cell is not None:
            cell.set_title(title)

    # ------------------------------------------------------------------ #
    #  单画面放大
    # ------------------------------------------------------------------ #

    def set_zoom(self, index: Optional[int]) -> bool:
        """把某个通道放大铺满整个网格区域（不重建窗口，播放不中断）。"""
        if index is not None and index not in self._cells:
            return False
        self._zoom = index

        if index is None:
            for row in self._rows:
                row.setVisible(True)
                for i in range(row.layout().count()):
                    w = row.layout().itemAt(i).widget()
                    if w is not None:
                        w.setVisible(True)
            self._apply_selection_visibility()
            return True

        for row in self._rows:
            lay = row.layout()
            visible_count = 0
            target_row = False
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if w is None:
                    continue
                if getattr(w, "index", None) == index:
                    target_row = True
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if w is None:
                    continue
                w.setVisible(target_row and getattr(w, "index", None) == index)
                if w.isVisible():
                    visible_count += 1
            row.setVisible(target_row)
        return True

    def _apply_selection_visibility(self) -> None:
        for cell in self._cells.values():
            cell.setVisible(True)
