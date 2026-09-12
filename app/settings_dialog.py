"""配置弹窗：通道表格 + 全局参数 + 导入/导出。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import (
    DEFAULT_RECORD_REL,
    DEFAULT_SNAPSHOT_REL,
    AppConfig,
    ChannelConfig,
    store_dir,
)
from .constants import (
    FIT_KEEP,
    FIT_STRETCH,
    FIT_TEXT,
    HW_DECODE_TEXT,
    MAX_CHANNELS,
    RECORD_MUX_TEXT,
)

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def _is_url(token: str) -> bool:
    return bool(_URL_RE.match(token.strip()))


class _BatchImportDialog(QDialog):
    """批量粘贴流地址。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量导入流地址")
        self.resize(560, 380)

        lay = QVBoxLayout(self)
        lay.addWidget(
            QLabel(
                "每行一个通道，支持以下格式：\n"
                "    名称,流地址      （逗号、中文逗号、制表符分隔）\n"
                "    名称 流地址      （空格分隔）\n"
                "    流地址           （只有地址时自动命名）\n"
                "以 # 开头的行会被忽略。"
            )
        )
        self.edit = QPlainTextEdit(self)
        self.edit.setPlaceholderText(
            "大门,rtsp://192.168.1.64:554/Streaming/Channels/101\n"
            "车间,rtsp://192.168.1.65:554/Streaming/Channels/101\n"
            "http://192.168.1.66:8080/live.flv"
        )
        lay.addWidget(self.edit, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("导入")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def rows(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for raw in self.edit.toPlainText().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            name, url = "", ""
            if "," in line or "，" in line or "\t" in line:
                parts = re.split(r"[,，\t]", line, maxsplit=1)
                name, url = parts[0].strip(), parts[1].strip()
            else:
                tokens = line.split()
                if len(tokens) >= 2 and not _is_url(tokens[0]) and _is_url(tokens[-1]):
                    name = " ".join(tokens[:-1])
                    url = tokens[-1]
                else:
                    url = line
            if url:
                out.append((name, url))
        return out


class SettingsDialog(QDialog):
    """配置对话框。工作副本模式：取消即全部丢弃。"""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("配置")
        self.resize(880, 620)
        self._source = config
        self._cfg = config.clone()
        self._muted_boxes: List[QCheckBox] = []
        self._vol_boxes: List[QSpinBox] = []

        root = QVBoxLayout(self)
        self.tabs = QTabWidget(self)

        self.tabs.addTab(self._build_channels_tab(), "通道配置")
        self.tabs.addTab(self._build_playback_tab(), "播放设置")
        self.tabs.addTab(self._build_reconnect_tab(), "断流重连")
        self.tabs.addTab(self._build_paths_tab(), "目录与录制")
        self.tabs.addTab(self._build_ui_tab(), "界面")
        root.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        self.btn_import = QPushButton("导入配置…")
        self.btn_export = QPushButton("导出配置…")
        self.btn_reset = QPushButton("恢复默认")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_export.clicked.connect(self._on_export)
        self.btn_reset.clicked.connect(self._on_reset)
        bar.addWidget(self.btn_import)
        bar.addWidget(self.btn_export)
        bar.addWidget(self.btn_reset)
        bar.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        bar.addWidget(buttons)
        root.addLayout(bar)

    # ================================================================== #
    #  通道配置页
    # ================================================================== #

    def _build_channels_tab(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)

        top = QHBoxLayout()
        top.addWidget(
            QLabel(f"最多 {MAX_CHANNELS} 路。只有「已勾选 + 填了地址」的通道才会出现在画面里。")
        )
        top.addStretch(1)
        for text, fn in (
            ("全部启用", lambda: self._set_all(True)),
            ("全部禁用", lambda: self._set_all(False)),
            ("清空", self._clear_all),
            ("批量导入地址…", self._on_batch),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(fn)
            top.addWidget(btn)
        lay.addLayout(top)
        lay.addWidget(
            QLabel(
                "💡 音量/静音：只有【未勾选「静音」】的通道才会出声。多路同时出声会互相干扰，"
                "建议只留一路出声（主界面工具栏有「🎧 仅此路出声」按钮）。"
            )
        )

        table = QTableWidget(MAX_CHANNELS, 5, page)
        table.setHorizontalHeaderLabels(["启用", "通道名称", "流地址 (URL)", "音量", "静音"])
        table.verticalHeader().setDefaultSectionSize(28)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 54)
        table.setColumnWidth(1, 170)
        table.setColumnWidth(3, 96)
        table.setColumnWidth(4, 56)

        self._table = table
        for i, ch in enumerate(self._cfg.channels):
            self._fill_row(table, i, ch)
        lay.addWidget(table, 1)
        return page

    def _fill_row(self, table: QTableWidget, i: int, ch: ChannelConfig) -> None:
        enable = QCheckBox()
        enable.setChecked(ch.enabled)
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.addWidget(enable)
        table.setCellWidget(i, 0, wrap)

        table.setItem(i, 1, QTableWidgetItem(ch.name))
        table.setItem(i, 2, QTableWidgetItem(ch.url))

        vol = QSpinBox()
        vol.setRange(0, 200)
        vol.setValue(ch.volume)
        vol.setSuffix(" %")
        table.setCellWidget(i, 3, vol)
        self._vol_boxes.append(vol)

        muted = QCheckBox()
        muted.setChecked(ch.muted)
        mwrap = QWidget()
        ml = QHBoxLayout(mwrap)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(muted)
        table.setCellWidget(i, 4, mwrap)
        self._muted_boxes.append(muted)

        self._enable_boxes = getattr(self, "_enable_boxes", [])
        self._enable_boxes.append(enable)

        # 名称 / 地址单元格允许直接编辑
        for col in (1, 2):
            item = table.item(i, col)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )

    def _collect_channels(self) -> None:
        self._table.clearFocus()  # 让正在编辑的单元格先提交
        for i, ch in enumerate(self._cfg.channels):
            ch.enabled = self._enable_boxes[i].isChecked()
            item_name = self._table.item(i, 1)
            item_url = self._table.item(i, 2)
            ch.name = (item_name.text() if item_name else "").strip()
            ch.url = (item_url.text() if item_url else "").strip()
            ch.volume = self._vol_boxes[i].value()
            ch.muted = self._muted_boxes[i].isChecked()

    def _set_all(self, value: bool) -> None:
        for box in self._enable_boxes:
            box.setChecked(value)

    def _clear_all(self) -> None:
        for i in range(MAX_CHANNELS):
            self._enable_boxes[i].setChecked(False)
            self._table.item(i, 1).setText("")
            self._table.item(i, 2).setText("")
            self._vol_boxes[i].setValue(80)
            self._muted_boxes[i].setChecked(True)

    def _on_batch(self) -> None:
        dlg = _BatchImportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rows = dlg.rows()
        if not rows:
            QMessageBox.information(self, "批量导入", "没有解析到有效的流地址。")
            return
        self._collect_channels()
        start = next(
            (i for i, ch in enumerate(self._cfg.channels) if not ch.url.strip()), 0
        )
        used = 0
        for offset, (name, url) in enumerate(rows):
            i = start + offset
            if i >= MAX_CHANNELS:
                break
            self._enable_boxes[i].setChecked(True)
            self._table.item(i, 1).setText(name or f"通道 {i + 1}")
            self._table.item(i, 2).setText(url)
            used += 1
        skipped = len(rows) - used
        msg = f"已导入 {used} 路。"
        if skipped > 0:
            msg += f"\n有 {skipped} 路超出 {MAX_CHANNELS} 路上限，已忽略。"
        QMessageBox.information(self, "批量导入", msg)

    # ================================================================== #
    #  其它设置页
    # ================================================================== #

    def _build_playback_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.sp_caching = QSpinBox()
        self.sp_caching.setRange(0, 60000)
        self.sp_caching.setSingleStep(50)
        self.sp_caching.setSuffix(" ms")
        self.sp_caching.setValue(self._cfg.network_caching)
        form.addRow("网络缓存 (network-caching)", self.sp_caching)
        form.addRow(
            "", QLabel("局域网建议 200~500ms，公网/弱网可调到 1000~3000ms。数值越大越抗抖动但延迟越高。")
        )

        self.cb_rtsp_tcp = QCheckBox("RTSP 强制走 TCP（推荐，穿透 NAT / 抗丢包更好）")
        self.cb_rtsp_tcp.setChecked(self._cfg.rtsp_tcp)
        form.addRow("RTSP 传输", self.cb_rtsp_tcp)

        self.cb_hw = QComboBox()
        for key, text in HW_DECODE_TEXT.items():
            self.cb_hw.addItem(text, key)
        self._select_data(self.cb_hw, self._cfg.hw_decode)
        form.addRow("硬件解码", self.cb_hw)
        form.addRow(
            "",
            QLabel("多路 1080P 时开启硬解可显著降低 CPU 占用；若出现花屏/绿屏请改为「关闭」。"),
        )

        self.cb_fit = QComboBox()
        for key in (FIT_KEEP, FIT_STRETCH):
            self.cb_fit.addItem(FIT_TEXT[key], key)
        self._select_data(self.cb_fit, self._cfg.fit)
        form.addRow("视频填充方式", self.cb_fit)
        return page

    def _build_reconnect_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.cb_reconnect = QCheckBox("断流后自动重连")
        self.cb_reconnect.setChecked(self._cfg.auto_reconnect)
        form.addRow("自动重连", self.cb_reconnect)

        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(1, 120)
        self.sp_interval.setSuffix(" 秒")
        self.sp_interval.setValue(self._cfg.reconnect_interval)
        form.addRow("首次重连间隔", self.sp_interval)
        form.addRow("", QLabel("失败后会按 1x / 2x / 4x … 指数退避，最长 60 秒一次。"))

        self.sp_retries = QSpinBox()
        self.sp_retries.setRange(0, 9999)
        self.sp_retries.setSpecialValueText("无限重试")
        self.sp_retries.setValue(self._cfg.max_retries)
        form.addRow("最大重试次数", self.sp_retries)

        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(3, 300)
        self.sp_timeout.setSuffix(" 秒")
        self.sp_timeout.setValue(self._cfg.connect_timeout)
        form.addRow("连接超时", self.sp_timeout)
        form.addRow("", QLabel("超过该时间仍未出画面，判定为连接失败并触发重连。"))
        return page

    def _build_paths_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.ed_snapshot = QLineEdit(self._cfg.snapshot_dir_display())
        self.ed_record = QLineEdit(self._cfg.record_dir_display())
        form.addRow("截图目录", self._row_with_browse(self.ed_snapshot))
        form.addRow("录制目录", self._row_with_browse(self.ed_record))
        form.addRow(
            "",
            QLabel(
                "默认保存在【程序自己所在的目录】下的 snapshots\\ 和 recordings\\，\n"
                "换版本/挪动文件夹时会自动跟着走，不会写回旧版本目录。\n"
                "也可以点「浏览…」指定别的位置（会存成绝对路径）。"
            ),
        )

        self.cb_mux = QComboBox()
        for key, text in RECORD_MUX_TEXT.items():
            self.cb_mux.addItem(text, key)
        self._select_data(self.cb_mux, self._cfg.record_mux)
        form.addRow("录制封装格式", self.cb_mux)
        form.addRow(
            "",
            QLabel(
                "说明：libvlc 3.x 没有录制开关 API，录制通过 sout 管线实现：\n"
                "    #duplicate{dst=display,dst=std{access=file,mux=…,dst=…}}\n"
                "因此【开始/停止录制会让该通道重新连接一次（约 1 秒黑屏）】。\n"
                "直播流建议用 TS（默认，最稳）；MKV 容错性也很好；\n"
                "MP4 对直播流不友好（异常退出时文件可能损坏）。\n"
                "文件名自动为「通道名_时间戳.扩展名」，保存在上面的录制目录。"
            ),
        )
        return page

    def _build_ui_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)

        self.cb_autoplay = QCheckBox("程序启动后自动播放所有已配置通道")
        self.cb_autoplay.setChecked(self._cfg.autoplay_on_start)
        form.addRow("启动行为", self.cb_autoplay)

        self.cb_header = QCheckBox("显示通道标题栏（关闭后画面完全铺满）")
        self.cb_header.setChecked(self._cfg.show_header)
        form.addRow("通道标题栏", self.cb_header)

        self.cb_fill = QCheckBox("末行拉伸铺满（消除最后一行右侧的空白格）")
        self.cb_fill.setChecked(bool(getattr(self._cfg, "fill_last_row", False)))
        form.addRow("末行", self.cb_fill)

        self.cb_zoom_fs = QCheckBox("双击画面 = 单画面全屏（隐藏工具栏/菜单栏/状态栏）")
        self.cb_zoom_fs.setChecked(bool(getattr(self._cfg, "zoom_fullscreen", True)))
        form.addRow("双击行为", self.cb_zoom_fs)
        form.addRow(
            "",
            QLabel(
                "勾选后：双击某路画面 → 该路铺满整个屏幕；再次双击或按 Esc 还原。\n"
                "取消勾选：双击只在窗口内把该路放大铺满网格区，保留工具栏。"
            ),
        )
        return page

    # ================================================================== #

    def _row_with_browse(self, line: QLineEdit) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(line, 1)
        btn = QPushButton("浏览…")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._browse(line))
        lay.addWidget(btn)
        return wrap

    def _browse(self, line: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择目录", line.text() or str(Path.home()))
        if path:
            line.setText(path)

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ================================================================== #

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON 配置 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            imported = AppConfig.from_dict(data)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", f"无法解析配置文件：\n{exc}")
            return
        self._cfg = imported
        self._reload_from_config()
        QMessageBox.information(self, "导入配置", "配置已载入，点击「确定」后生效。")

    def _on_export(self) -> None:
        self._collect_channels()
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "multiview-config.json", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            self._cfg.save(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出配置", f"已导出到：\n{path}")

    def _on_reset(self) -> None:
        if (
            QMessageBox.question(
                self, "恢复默认", "确定要恢复为默认配置吗？（当前填写内容将丢失）"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._cfg = AppConfig()
        self._reload_from_config()

    def _reload_from_config(self) -> None:
        """把 self._cfg 的内容回填到所有控件。"""
        self._cfg.normalize()
        for i, ch in enumerate(self._cfg.channels):
            self._enable_boxes[i].setChecked(ch.enabled)
            self._table.item(i, 1).setText(ch.name)
            self._table.item(i, 2).setText(ch.url)
            self._vol_boxes[i].setValue(ch.volume)
            self._muted_boxes[i].setChecked(ch.muted)
        self.sp_caching.setValue(self._cfg.network_caching)
        self.cb_rtsp_tcp.setChecked(self._cfg.rtsp_tcp)
        self._select_data(self.cb_hw, self._cfg.hw_decode)
        self._select_data(self.cb_fit, self._cfg.fit)
        self.cb_reconnect.setChecked(self._cfg.auto_reconnect)
        self.sp_interval.setValue(self._cfg.reconnect_interval)
        self.sp_retries.setValue(self._cfg.max_retries)
        self.sp_timeout.setValue(self._cfg.connect_timeout)
        self.ed_snapshot.setText(self._cfg.snapshot_dir_display())
        self.ed_record.setText(self._cfg.record_dir_display())
        self._select_data(self.cb_mux, self._cfg.record_mux)
        self.cb_autoplay.setChecked(self._cfg.autoplay_on_start)
        self.cb_header.setChecked(self._cfg.show_header)
        self.cb_fill.setChecked(bool(getattr(self._cfg, "fill_last_row", False)))
        self.cb_zoom_fs.setChecked(bool(getattr(self._cfg, "zoom_fullscreen", True)))

    def _on_accept(self) -> None:
        self._collect_channels()
        self._cfg.network_caching = self.sp_caching.value()
        self._cfg.rtsp_tcp = self.cb_rtsp_tcp.isChecked()
        self._cfg.hw_decode = self.cb_hw.currentData()
        self._cfg.fit = self.cb_fit.currentData()
        self._cfg.auto_reconnect = self.cb_reconnect.isChecked()
        self._cfg.reconnect_interval = self.sp_interval.value()
        self._cfg.max_retries = self.sp_retries.value()
        self._cfg.connect_timeout = self.sp_timeout.value()
        snap_text = self.ed_snapshot.text().strip()
        rec_text = self.ed_record.text().strip()
        self._cfg.snapshot_dir = (
            store_dir(snap_text, DEFAULT_SNAPSHOT_REL) if snap_text else DEFAULT_SNAPSHOT_REL
        )
        self._cfg.record_dir = (
            store_dir(rec_text, DEFAULT_RECORD_REL) if rec_text else DEFAULT_RECORD_REL
        )
        self._cfg.record_mux = self.cb_mux.currentData()
        self._cfg.autoplay_on_start = self.cb_autoplay.isChecked()
        self._cfg.show_header = self.cb_header.isChecked()
        self._cfg.fill_last_row = self.cb_fill.isChecked()
        self._cfg.zoom_fullscreen = self.cb_zoom_fs.isChecked()
        self._cfg.normalize()
        self.accept()

    # ------------------------------------------------------------------ #

    def result_config(self) -> AppConfig:
        return self._cfg
