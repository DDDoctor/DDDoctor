"""主窗口：工具栏、网格画面、状态栏、截图/录制/全屏等操作。"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QWidget,
)

from .config import AppConfig
from .constants import (
    APP_TITLE,
    APP_VERSION,
    FIT_STRETCH,
    MAX_CHANNELS,
    STATE_IDLE,
    STATE_PLAYING,
)
from .dispatch import get_pool
from .paths import config_path
from .player import ChannelPlayer, VlcEngine
from .settings_dialog import SettingsDialog
from .sysinfo import format_mb, working_set_mb
from .vlc_runtime import describe as describe_vlc
from .wall import VideoWall

log = logging.getLogger(__name__)

_ENGINE_KEYS = ("network_caching", "rtsp_tcp", "hw_decode", "record_dir")


def _safe_name(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text).strip(" ._")
    return cleaned or "channel"


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.players: Dict[int, ChannelPlayer] = {}
        self._playing = False
        self._global_mute = False
        self._selected: Optional[int] = None
        self._zoom: Optional[int] = None
        self._zoomed_fullscreen = False
        self._was_fullscreen = False
        self._snap_dir: Optional[Path] = None
        self._snap_ok = 0
        self._snap_failed: List[int] = []
        self._snap_recording: List[int] = []
        self._snap_pending = 0
        self._engine: Optional[VlcEngine] = None
        #: 阻塞的 libvlc 调用全部丢到这里执行，保证 UI 线程不被卡住
        self._dispatchers = get_pool()

        self.setWindowTitle(f"{APP_TITLE} v{APP_VERSION}")
        self.resize(1440, 860)
        self.setMinimumSize(720, 480)

        self.wall = VideoWall(self)
        self.setCentralWidget(self.wall)
        self.wall.cellClicked.connect(self._on_cell_clicked)
        self.wall.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.wall.cellResized.connect(self._on_cell_resized)

        self._build_toolbar()
        self._build_statusbar()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self._create_engine()
        self._build_players()
        self.wall.set_header_visible(self.config.show_header)
        self._rebuild_wall()

        if self.config.autoplay_on_start and self.config.active_channels():
            QTimer.singleShot(300, self.play_all)
        log.info(
            "主窗口就绪：%s 路通道上屏，网格 %s",
            len(self.wall.cells),
            self.config.active_channels(),
        )

    # ================================================================== #
    #  引擎 / 播放器
    # ================================================================== #

    def _create_engine(self) -> None:
        self._engine = VlcEngine(self.config)

    def _build_players(self) -> None:
        assert self._engine is not None
        for index in range(MAX_CHANNELS):
            player = ChannelPlayer(
                index, self._engine, self._dispatchers.for_index(index), self
            )
            player.statusChanged.connect(self._on_player_status)
            player.snapshotDone.connect(self._on_snapshot_done)
            self.players[index] = player

    def _destroy_players(self) -> None:
        for player in self.players.values():
            player.destroy()
        self.players.clear()

    def _release_engine_async(self, engine: Optional[VlcEngine]) -> None:
        """释放 libvlc 实例同样是阻塞操作（要等所有输入线程结束），丢到后台。"""
        if engine is None:
            return
        self._dispatchers.for_index(0).post("engine-release", engine.release)

    def _restart_engine(self) -> None:
        was_playing = self._playing
        self._playing = False
        self._destroy_players()
        old_engine, self._engine = self._engine, None
        self._release_engine_async(old_engine)
        self._create_engine()
        self._build_players()
        self._rebuild_wall()
        if was_playing:
            self.play_all()

    # ================================================================== #
    #  界面构建
    # ================================================================== #

    def _build_toolbar(self) -> None:
        bar = QToolBar("主工具栏", self)
        bar.setMovable(False)
        bar.setIconSize(bar.iconSize())
        self.addToolBar(bar)
        self._toolbar = bar

        def add(text: str, slot, tip: str = "", checkable: bool = False) -> QPushButton:
            btn = QPushButton(text)
            btn.setCheckable(checkable)
            btn.clicked.connect(slot)
            if tip:
                btn.setToolTip(tip)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.addWidget(btn)
            return btn

        add("▶ 播放全部", self.play_all, "播放所有已启用通道 (Space)")
        add("■ 停止全部", self.stop_all, "停止所有通道")
        self.btn_mute = add("🔊 全局静音", self._toggle_global_mute, "一键静音/恢复所有通道", True)
        add("🎧 仅此路出声", self.solo_audio, "只让「当前通道」出声，其余全部静音")
        add("🔇 当前通道静音", self.toggle_channel_mute, "切换当前通道的静音状态 (Ctrl+M)")

        bar.addSeparator()
        add("配置…", self.open_settings, "打开配置弹窗 (Ctrl+,)")

        bar.addSeparator()
        bar.addWidget(QLabel(" 当前通道："))
        self.cb_channel = QComboBox()
        self.cb_channel.setMinimumWidth(180)
        self.cb_channel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cb_channel.currentIndexChanged.connect(self._on_combo_changed)
        bar.addWidget(self.cb_channel)

        bar.addSeparator()
        add("🔍 放大/还原", self.toggle_zoom, "把当前通道铺满整个窗口 (Ctrl+F)")
        self.btn_record = add("⏺ 录制", self.toggle_record, "对当前通道开始/停止录制 (Ctrl+R)")
        add("📷 截图", self.take_snapshot, "对当前通道截图 (Ctrl+S)")

        bar.addSeparator()
        add("全屏", self.toggle_fullscreen, "全屏切换 (F11)")
        add("重启引擎", self._on_restart_engine, "VLC 卡死时重置播放引擎")

        # 菜单
        m_file = self.menuBar().addMenu("文件(&F)")
        self._action(m_file, "配置…", "Ctrl+,", self.open_settings)
        self._action(m_file, "导入配置…", None, self.import_config)
        self._action(m_file, "导出配置…", None, self.export_config)
        m_file.addSeparator()
        self._action(m_file, "打开截图目录", None, lambda: self._open_dir(self.config.snapshot_dir_path()))
        self._action(m_file, "打开录制目录", None, lambda: self._open_dir(self.config.record_dir_path()))
        m_file.addSeparator()
        self._action(m_file, "退出", "Ctrl+Q", self.close)

        m_view = self.menuBar().addMenu("视图(&V)")
        self._action(m_view, "全屏切换", "F11", self.toggle_fullscreen)
        self._action(m_view, "放大当前通道", "Ctrl+F", self.toggle_zoom)
        self._action(m_view, "取消放大", None, lambda: self._set_zoom(None))
        m_view.addSeparator()
        self._action(m_view, "仅当前通道出声", None, self.solo_audio)
        self._action(m_view, "切换当前通道静音", "Ctrl+M", self.toggle_channel_mute)
        m_view.addSeparator()
        self.act_header = self._action(m_view, "显示通道标题栏", None, self._toggle_header, checkable=True)
        self.act_header.setChecked(self.config.show_header)
        self.act_fill = self._action(m_view, "末行拉伸铺满", None, self._toggle_fill, checkable=True)
        self.act_fill.setChecked(self.config.fill_last_row)

        m_help = self.menuBar().addMenu("帮助(&H)")
        self._action(m_help, "快捷键说明", None, self._show_help)
        self._action(m_help, "关于", None, self._show_about)

    def _action(self, menu, text: str, shortcut: Optional[str], slot, checkable: bool = False) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.setCheckable(checkable)
        act.triggered.connect(slot)
        menu.addAction(act)
        self.addAction(act)
        return act

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self.lbl_channels = QLabel("")
        self.lbl_mem = QLabel("")
        self.lbl_mem.setStyleSheet("color:#8b93a1;")
        self.lbl_mem.setToolTip("本程序占用的物理内存。多路 1080P 每路约 200-250MB，可用它判断机器是否吃得消。")
        self.lbl_vlc = QLabel("")
        self.lbl_vlc.setStyleSheet("color:#8b93a1;")
        sb.addWidget(self.lbl_channels)
        sb.addPermanentWidget(self.lbl_mem)
        sb.addPermanentWidget(self.lbl_vlc)
        self.lbl_vlc.setText(describe_vlc())

    # ================================================================== #
    #  网格
    # ================================================================== #

    def _rebuild_wall(self) -> None:
        entries = [
            (i, self.config.channels[i].display_name(i)) for i in self.config.active_channels()
        ]
        # 用「画面区」的真实比例来算网格（要扣掉菜单栏/工具栏/状态栏）
        aspect = self.wall.width() / max(self.wall.height(), 1)
        if not (0.5 <= aspect <= 8.0):
            aspect = self.width() / max(self.height(), 1)
        self.wall.rebuild(
            entries, fill_last_row=self.config.fill_last_row, screen_aspect=aspect
        )
        for index, cell in self.wall.cells.items():
            player = self.players.get(index)
            if player is not None:
                player.bind_widget(cell.video_widget())
            self._apply_channel_audio(index)
            cell.set_state(STATE_IDLE, "")
            cell.set_mute_hint(self.config.channels[index].muted, self.config.channels[index].volume)

        self._refresh_combo()
        if self._zoomed_fullscreen:
            self._leave_zoom_fullscreen()
        self._zoom = None
        if self._selected not in self.wall.cells:
            self._selected = entries[0][0] if entries else None
        self._refresh_selection()
        self._refresh_status()

    def _refresh_combo(self) -> None:
        self.cb_channel.blockSignals(True)
        self.cb_channel.clear()
        for index, cell in sorted(self.wall.cells.items()):
            self.cb_channel.addItem(
                f"{index + 1:02d} · {self.config.channels[index].display_name(index)}", index
            )
        idx = self.cb_channel.findData(self._selected)
        self.cb_channel.setCurrentIndex(idx if idx >= 0 else -1)
        self.cb_channel.blockSignals(False)

    def _refresh_selection(self) -> None:
        self.wall.set_selected(self._selected)
        playing = self.players.get(self._selected) if self._selected is not None else None
        if playing is not None:
            self.btn_record.setText("⏹ 停止录制" if playing.recording else "⏺ 录制")

    # ================================================================== #
    #  播放控制
    # ================================================================== #

    def _apply_channel_audio(self, index: int) -> None:
        player = self.players.get(index)
        if player is None:
            return
        ch = self.config.channels[index]
        muted = self._global_mute or ch.muted
        fit = self.config.effective_fit(index)
        player.apply_config(ch.volume, muted, fit)
        cell = self.wall.cells.get(index)
        if cell is not None:
            cell.set_mute_hint(muted, ch.volume)
        self._apply_stretch(index)

    def _apply_stretch(self, index: int) -> None:
        """「拉伸铺满」需要把显示宽高比设成画面区的宽高比。"""
        if self.config.effective_fit(index) != FIT_STRETCH:
            return
        player = self.players.get(index)
        cell = self.wall.cells.get(index)
        if player is None or cell is None:
            return
        player.set_stretch(cell.video.width(), cell.video.height())

    def _on_cell_resized(self, index: int, width: int, height: int) -> None:
        player = self.players.get(index)
        if player is None:
            return
        if self.config.effective_fit(index) == FIT_STRETCH:
            player.set_stretch(width, height)

    def play_all(self) -> None:
        if not self.wall.cells:
            self._flash("没有可播放的通道，请先在「配置」中填写流地址。")
            return
        self._playing = True
        indices = sorted(self.wall.cells)
        # 十几路同时起流会让 CPU 瞬间打满，错开 250ms 起一路更平滑
        stagger = 250 if len(indices) > 6 else 0
        for order, index in enumerate(indices):
            self._apply_channel_audio(index)
            if stagger:
                QTimer.singleShot(order * stagger, lambda i=index: self._start_channel(i))
            else:
                self._start_channel(index)
        self._flash(f"已开始播放 {len(indices)} 路通道。")

    def _start_channel(self, index: int) -> None:
        """起流（可能被错峰延迟调用，需要重新确认状态）。"""
        if not self._playing:
            return
        if index not in self.wall.cells:
            return
        player = self.players.get(index)
        if player is None:
            return
        player.play(self.config.channels[index].url, reset_retries=True)

    def stop_all(self) -> None:
        self._playing = False
        for player in self.players.values():
            player.stop()
        for cell in self.wall.cells.values():
            cell.set_state(STATE_IDLE, "")
        self._refresh_selection()
        self._refresh_status()
        self._flash("已停止全部通道。")

    def _toggle_global_mute(self) -> None:
        self._global_mute = self.btn_mute.isChecked()
        self.btn_mute.setText("🔇 已静音" if self._global_mute else "🔊 全局静音")
        for index in self.wall.cells:
            self._apply_channel_audio(index)

    def solo_audio(self) -> None:
        """只让当前通道出声（监控墙的常用操作）。"""
        if self._selected is None or self._selected not in self.wall.cells:
            self._flash("请先在「当前通道」里选一个通道。")
            return
        self._global_mute = False
        self.btn_mute.setChecked(False)
        self.btn_mute.setText("🔊 全局静音")
        for index in self.wall.cells:
            self.config.channels[index].muted = index != self._selected
            self._apply_channel_audio(index)
        self._save_quiet()
        name = self.config.channels[self._selected].display_name(self._selected)
        self._flash(f"只有「{name}」在出声，其余通道已静音。")

    def toggle_channel_mute(self) -> None:
        if self._selected is None or self._selected not in self.wall.cells:
            self._flash("请先在「当前通道」里选一个通道。")
            return
        ch = self.config.channels[self._selected]
        ch.muted = not ch.muted
        self._apply_channel_audio(self._selected)
        self._save_quiet()
        name = ch.display_name(self._selected)
        self._flash(f"「{name}」已{'静音' if ch.muted else '取消静音'}。")

    def _on_restart_engine(self) -> None:
        self._restart_engine()
        self._flash("播放引擎已重置。")

    # ================================================================== #
    #  选择 / 放大
    # ================================================================== #

    def _on_combo_changed(self, _pos: int) -> None:
        data = self.cb_channel.currentData()
        if data is not None:
            self._selected = int(data)
            self._refresh_selection()

    def _on_cell_clicked(self, index: int) -> None:
        self._selected = index
        self._refresh_selection()
        idx = self.cb_channel.findData(index)
        if idx >= 0:
            self.cb_channel.blockSignals(True)
            self.cb_channel.setCurrentIndex(idx)
            self.cb_channel.blockSignals(False)

    def _on_cell_double_clicked(self, index: int) -> None:
        self._selected = index
        self._refresh_selection()
        if self._zoom == index:
            self._set_zoom(None)
        else:
            self._set_zoom(index)

    def toggle_zoom(self) -> None:
        if self._selected is None:
            self._flash("请先选择一个通道。")
            return
        self._set_zoom(None if self._zoom == self._selected else self._selected)

    def _set_zoom(self, index: Optional[int]) -> None:
        if index is None:
            self.wall.set_zoom(None)
            self._zoom = None
            self._leave_zoom_fullscreen()
            self._refresh_status()
            self._flash("已恢复网格视图。")
            return
        if self.wall.set_zoom(index):
            self._zoom = index
            self._enter_zoom_fullscreen()
            self._refresh_status()
            self._flash(
                f"已放大：{self.config.channels[index].display_name(index)}"
                "（双击或按 Esc 还原）"
            )
        else:
            self._flash("该通道当前不在画面中。")

    # --- 单画面全屏：隐藏工具栏/菜单栏/状态栏，让画面真正铺满整个屏幕 --- #

    def _enter_zoom_fullscreen(self) -> None:
        if not self.config.zoom_fullscreen or self._zoomed_fullscreen:
            return
        self._zoomed_fullscreen = True
        self._was_fullscreen = self.isFullScreen()
        self.menuBar().setVisible(False)
        self._toolbar.setVisible(False)
        self.statusBar().setVisible(False)
        if not self._was_fullscreen:
            self.showFullScreen()

    def _leave_zoom_fullscreen(self) -> None:
        if not self._zoomed_fullscreen:
            return
        self._zoomed_fullscreen = False
        self.menuBar().setVisible(True)
        self._toolbar.setVisible(True)
        self.statusBar().setVisible(True)
        if not self._was_fullscreen and self.isFullScreen():
            self.showNormal()

    # ================================================================== #
    #  截图 / 录制
    # ================================================================== #

    def take_snapshot(self) -> None:
        targets = self._targets()
        if not targets:
            self._flash("没有可截图的通道。")
            return
        out_dir = self.config.snapshot_dir_path()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._snap_dir = out_dir
        self._snap_ok = 0
        self._snap_failed = []
        self._snap_recording = []
        self._snap_pending = 0
        for index in targets:
            player = self.players.get(index)
            if player is None or player.state != STATE_PLAYING:
                self._snap_failed.append(index)
                continue
            if player.recording:
                # VLC 在 sout 录制模式下不注册可截图的 vout，属于已知限制
                self._snap_recording.append(index)
                continue
            name = _safe_name(self.config.channels[index].display_name(index))
            self._snap_pending += 1
            player.take_snapshot(out_dir / f"{name}_{stamp}.png")
        if self._snap_pending == 0:
            self._finish_snapshot()
        else:
            self._flash(f"正在截图（{self._snap_pending} 路）…")

    def _on_snapshot_done(self, index: int, ok: bool, _path: str) -> None:
        self._snap_pending = max(0, self._snap_pending - 1)
        if ok:
            self._snap_ok += 1
        else:
            self._snap_failed.append(index)
        if self._snap_pending == 0:
            self._finish_snapshot()

    def _finish_snapshot(self) -> None:
        out_dir = getattr(self, "_snap_dir", self.config.snapshot_dir_path())
        msg = f"截图成功 {self._snap_ok} 张，保存在：\n{out_dir}"
        if self._snap_recording:
            names = "、".join(str(i + 1) for i in self._snap_recording)
            msg += f"\n\n以下通道正在录制，VLC 在 sout 录制模式下无法截图，请先停止录制：{names}"
        if self._snap_failed:
            names = "、".join(str(i + 1) for i in self._snap_failed)
            msg += f"\n\n以下通道未截到画面（未在播放或截图失败）：{names}"
        self._flash(f"截图完成：{self._snap_ok} 张")
        QMessageBox.information(self, "截图", msg)

    def toggle_record(self) -> None:
        if self._selected is None:
            self._flash("请先选择一个通道。")
            return
        player = self.players.get(self._selected)
        if player is None:
            return
        if player.recording:
            player.set_recording(False)
            self._flash("已停止录制。")
        else:
            if player.state != STATE_PLAYING:
                QMessageBox.warning(self, "录制", "该通道当前没有在播放，无法录制。")
                return
            name = _safe_name(self.config.channels[self._selected].display_name(self._selected))
            player.set_record_alias(name, "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
            if player.set_recording(True):
                self._flash(f"开始录制（该通道会重连一次）：{player.record_path}")
            else:
                self._flash("开始录制失败。")
        self._refresh_selection()

    def _targets(self) -> List[int]:
        if self._selected is not None and self._selected in self.wall.cells:
            return [self._selected]
        return sorted(self.wall.cells.keys())

    # ================================================================== #
    #  配置
    # ================================================================== #

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self)
        if not dlg.exec():
            return
        new_cfg = dlg.result_config()
        engine_changed = any(
            getattr(self.config, key) != getattr(new_cfg, key) for key in _ENGINE_KEYS
        )
        self.config = new_cfg
        try:
            self.config.save(config_path())
        except Exception as exc:  # noqa: BLE001
            log.warning("保存配置失败: %s", exc)
            self._flash(f"配置已应用，但保存到文件失败：{exc}")

        self.wall.set_header_visible(self.config.show_header)
        self._apply_ui_flags()

        if engine_changed:
            self._restart_engine()
        else:
            was_playing = self._playing
            self.stop_all()
            self._rebuild_wall()
            if was_playing:
                self.play_all()
        self._flash("配置已更新。")

    def import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入配置", "", "JSON 配置 (*.json);;所有文件 (*)")
        if not path:
            return
        try:
            imported = AppConfig.load(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        if not any(ch.active() for ch in imported.channels):
            if (
                QMessageBox.question(
                    self, "导入配置", "该配置里没有任何启用的通道，仍然导入吗？"
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
        self.config = imported
        try:
            self.config.save(config_path())
        except Exception:  # noqa: BLE001
            pass
        self._apply_ui_flags()
        self._restart_engine()
        self._flash(f"已导入配置：{path}")

    def export_config(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", "multiview-config.json", "JSON 配置 (*.json)"
        )
        if not path:
            return
        try:
            self.config.save(Path(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self._flash(f"已导出配置：{path}")

    def _toggle_header(self) -> None:
        self.config.show_header = self.act_header.isChecked()
        self.wall.set_header_visible(self.config.show_header)
        self._save_quiet()

    def _toggle_fill(self) -> None:
        self.config.fill_last_row = self.act_fill.isChecked()
        was_playing = self._playing
        self.stop_all()
        self._rebuild_wall()
        if was_playing:
            self.play_all()
        self._save_quiet()

    def _apply_ui_flags(self) -> None:
        self.wall.set_header_visible(self.config.show_header)
        self.act_header.setChecked(self.config.show_header)
        self.act_fill.setChecked(self.config.fill_last_row)

    def _save_quiet(self) -> None:
        try:
            self.config.save(config_path())
        except Exception:  # noqa: BLE001
            pass

    # ================================================================== #
    #  状态
    # ================================================================== #

    def _on_player_status(self, index: int, state: str, detail: str) -> None:
        self.wall.update_cell_state(index, state, detail)
        cell = self.wall.cells.get(index)
        if cell is not None:
            cell.set_recording(self.players[index].recording)
        if index == self._selected:
            self.btn_record.setText(
                "⏹ 停止录制" if self.players[index].recording else "⏺ 录制"
            )
        self._refresh_status()

    def _refresh_status(self) -> None:
        total = len(self.wall.cells)
        online = 0
        for index in self.wall.cells:
            player = self.players.get(index)
            if player is not None and player.state == STATE_PLAYING:
                online += 1
        self.lbl_channels.setText(f"通道：{online}/{total} 在线（共配置 {MAX_CHANNELS} 路）")
        self.lbl_mem.setText(f"内存 {format_mb(working_set_mb())}")
        title = f"{APP_TITLE} v{APP_VERSION} — {online}/{total} 在线"
        if self._zoom is not None and 0 <= self._zoom < len(self.config.channels):
            title += f" — 放大：{self.config.channels[self._zoom].display_name(self._zoom)}"
        self.setWindowTitle(title)

    def _flash(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    # ================================================================== #
    #  其它
    # ================================================================== #

    def toggle_fullscreen(self) -> None:
        if self._zoom is not None:
            # 单画面全屏时按 F11 视作「还原」
            self._set_zoom(None)
            return
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def showEvent(self, event) -> None:  # noqa: N802
        """首次显示后按真实窗口比例重算一次网格（构造时部件尺寸还不准确）。"""
        super().showEvent(event)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            if not self._playing:
                QTimer.singleShot(50, self._rebuild_wall)

    def _open_dir(self, path: Path) -> None:
        import os

        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "打开目录", f"无法打开目录：\n{path}\n{exc}")

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "快捷键",
            "Space      播放全部 / 停止全部（交替）\n"
            "F11        全屏切换\n"
            "Esc        退出单画面全屏 / 还原放大 / 退出全屏\n"
            "Ctrl+F     放大或还原当前通道（单画面全屏）\n"
            "Ctrl+M     切换当前通道静音\n"
            "Ctrl+S     对当前通道截图\n"
            "Ctrl+R     对当前通道开始 / 停止录制\n"
            "Ctrl+,     打开配置弹窗\n"
            "双击画面   单画面全屏 / 还原（可在配置里改成「只在窗口内放大」）\n"
            "单击画面   选中该通道",
        )

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            f"{APP_TITLE} v{APP_VERSION}\n\n"
            f"基于 python-vlc (libvlc) + PySide6 构建，最多支持 {MAX_CHANNELS} 路视频流同屏。\n"
            f"{describe_vlc()}\n\n"
            f"配置文件：{config_path()}",
        )

    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_Space:
            if self._playing:
                self.stop_all()
            else:
                self.play_all()
            return
        if key == Qt.Key.Key_Escape:
            if self._zoom is not None:
                self._set_zoom(None)
            elif self.isFullScreen():
                self.showNormal()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._status_timer.stop()
        self._playing = False
        # 先隐藏：用户看到的是"瞬间关闭"，后面等多久都不影响观感
        self.hide()
        for player in self.players.values():
            player.stop()          # 只投递作业，立即返回
        self._destroy_players()    # 同上
        engine, self._engine = self._engine, None
        self._release_engine_async(engine)
        # 等 libvlc 干净地停下来再退出，否则进程会留下杀不掉的僵尸条目
        t0 = time.monotonic()
        done = self._dispatchers.shutdown(timeout_s=12.0)
        log.info(
            "关闭：后台收尾%s，耗时 %.2fs",
            "完成" if done else "超时放弃",
            time.monotonic() - t0,
        )
        event.accept()
