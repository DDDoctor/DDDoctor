"""VLC 播放内核：共享 libvlc 实例 + 每通道一个 MediaPlayer。

设计要点
--------
* 整个程序共用一个 ``vlc.Instance``，每个通道一个 ``MediaPlayer``，资源占用最低。
* libvlc 的事件回调运行在 VLC 自己的线程里，所有状态更新都通过 Qt 信号
  投递回主线程，避免跨线程操作界面。
* **所有可能阻塞的 libvlc 调用（stop / set_media / play / release）都提交到
  :mod:`app.dispatch` 的后台线程执行**，否则摄像头掉线时一次 stop() 就能把界面卡死几秒。
* 断流后按指数退避自动重连，并带「连接超时」看门狗，防止某个流永远卡在连接中。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import vlc
from PySide6.QtCore import QObject, QTimer, Signal

from .config import AppConfig
from .constants import (
    STATE_BUFFERING,
    STATE_CONNECTING,
    STATE_ERROR,
    STATE_IDLE,
    STATE_OFFLINE,
    STATE_PLAYING,
    STATE_RECONNECTING,
    STATE_TEXT,
)
from .dispatch import VlcDispatcher

log = logging.getLogger(__name__)

#: 缓冲百分比刷新节流（秒）—— VLC 的 buffering 事件非常密集，
#: 不节流会让 18 个画面每秒重绘几百次，直接把界面拖垮。
BUFFER_UI_INTERVAL = 0.5


# --------------------------------------------------------------------------- #
#  libvlc 实例
# --------------------------------------------------------------------------- #


class VlcEngine:
    """封装共享的 libvlc 实例，负责构造启动参数。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._instance: Optional[vlc.Instance] = None
        self.create()

    # ---------------------------------------------------------------- #

    def _build_args(self) -> List[str]:
        cfg = self._config
        args = [
            "--intf=dummy",             # 不加载任何界面插件
            "--no-video-title-show",
            "--no-snapshot-preview",
            "--no-stats",
            "--no-one-instance",
            "--no-osd",
            "--quiet",
            f"--avcodec-hw={cfg.hw_decode}",
            f"--network-caching={cfg.network_caching}",
            f"--live-caching={cfg.network_caching}",
            f"--file-caching={max(cfg.network_caching, 300)}",
            f"--input-record-path={cfg.record_dir_path()}",
        ]
        if cfg.rtsp_tcp:
            args.append("--rtsp-tcp")
        return args

    def create(self) -> None:
        self.release()
        args = self._build_args()
        log.info("创建 libvlc 实例: %s", " ".join(args))
        try:
            self._instance = vlc.Instance(args)
        except Exception:  # noqa: BLE001
            log.exception("使用自定义参数创建 libvlc 实例失败，退回默认参数")
            self._instance = vlc.Instance()
        if self._instance is None:
            raise RuntimeError("无法初始化 libvlc，请检查 VLC 运行库是否完整。")

    def release(self) -> None:
        if self._instance is not None:
            try:
                self._instance.release()
            except Exception:  # noqa: BLE001
                pass
            self._instance = None

    @property
    def instance(self) -> vlc.Instance:
        if self._instance is None:
            raise RuntimeError("libvlc 实例尚未创建")
        return self._instance

    @property
    def config(self) -> AppConfig:
        return self._config


# --------------------------------------------------------------------------- #
#  单通道播放器
# --------------------------------------------------------------------------- #


class ChannelPlayer(QObject):
    """一个通道 = 一个 MediaPlayer，绑定到一个 QWidget 的窗口句柄。"""

    #: (通道序号, 状态, 说明文字)
    statusChanged = Signal(int, str, str)
    #: 来自 VLC 线程的重连请求
    _reconnectRequested = Signal(str)
    #: 来自 VLC 线程的原始状态通知
    _vlcState = Signal(str)
    #: 后台起流任务真正开始执行（在主线程武装看门狗）
    _jobStarted = Signal()
    #: (通道序号, 是否成功, 文件路径)
    snapshotDone = Signal(int, bool, str)

    def __init__(
        self,
        index: int,
        engine: VlcEngine,
        dispatcher: VlcDispatcher,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self._engine = engine
        self._dispatch = dispatcher
        self._player: vlc.MediaPlayer = engine.instance.media_player_new()
        self._media: Optional[vlc.Media] = None

        self._url: str = ""
        self._should_play: bool = False
        self._manual_stop: bool = True
        self._retries: int = 0
        self._state: str = STATE_IDLE
        self._detail: str = ""
        self._started_at: float = 0.0
        self._last_buffer_ui: float = 0.0
        self._destroyed: bool = False

        self._volume: int = 80
        self._muted: bool = True
        self._fit: str = "keep"
        self._stretch_target: tuple = (0, 0)
        self._stretch_pending: bool = False

        self._recording: bool = False
        self._record_alias: str = ""
        self._record_stamp: str = ""
        self._record_path: Optional[Path] = None

        self._widget_id: Optional[int] = None

        # 事件管理器必须持有引用，否则回调会被回收
        self._events = self._player.event_manager()
        self._callbacks: list = []
        self._attach_events()

        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._do_reconnect)

        self._reconnectRequested.connect(self._schedule_reconnect)
        self._vlcState.connect(self._on_vlc_state)
        self._jobStarted.connect(self._on_job_started)

    # ------------------------------------------------------------------ #
    #  事件绑定
    # ------------------------------------------------------------------ #

    def _attach_events(self) -> None:
        et = vlc.EventType
        table = {
            et.MediaPlayerOpening: self._evt_opening,
            et.MediaPlayerBuffering: self._evt_buffering,
            et.MediaPlayerPlaying: self._evt_playing,
            et.MediaPlayerPaused: self._evt_buffering,
            et.MediaPlayerStopped: self._evt_stopped,
            et.MediaPlayerEndReached: self._evt_end,
            et.MediaPlayerEncounteredError: self._evt_error,
        }
        for event_type, handler in table.items():
            try:
                self._events.event_attach(event_type, handler)
                self._callbacks.append(handler)
            except Exception as exc:  # noqa: BLE001
                log.debug("绑定事件 %s 失败: %s", event_type, exc)

    def _release_events(self) -> None:
        try:
            self._events.event_detach(vlc.EventType.MediaPlayerOpening)
        except Exception:  # noqa: BLE001
            pass
        self._callbacks = []

    # --- 以下回调运行在 VLC 线程，只能 emit 信号 ------------------------- #

    def _evt_opening(self, _event) -> None:
        self._vlcState.emit(STATE_CONNECTING)

    def _evt_buffering(self, event) -> None:
        pct = ""
        try:
            pct = f"{event.u.media_player_buffering.new_cache}%"
        except Exception:  # noqa: BLE001
            pass
        self._vlcState.emit(f"{STATE_BUFFERING}|{pct}")

    def _evt_playing(self, _event) -> None:
        self._vlcState.emit(STATE_PLAYING)

    def _evt_stopped(self, _event) -> None:
        self._vlcState.emit("stopped")

    def _evt_end(self, _event) -> None:
        self._vlcState.emit("ended")

    def _evt_error(self, _event) -> None:
        log.warning("通道 %s 解码/连接出错", self.index + 1)
        self._vlcState.emit("error")

    # ------------------------------------------------------------------ #
    #  主线程侧的状态处理
    # ------------------------------------------------------------------ #

    def _on_vlc_state(self, raw: str) -> None:
        if self._destroyed:
            return
        if "|" in raw:
            state, detail = raw.split("|", 1)
        else:
            state, detail = raw, ""

        if state == STATE_PLAYING:
            was_retrying = self._retries > 0
            self._retries = 0
            self._watchdog.stop()
            self._retry_timer.stop()
            self._set_state(STATE_PLAYING, "重连成功" if was_retrying else "")

        elif state == STATE_CONNECTING:
            if self._state not in (STATE_PLAYING, STATE_BUFFERING):
                self._set_state(STATE_CONNECTING, "")

        elif state == STATE_BUFFERING:
            if self._state != STATE_PLAYING:
                now = time.monotonic()
                if self._state != STATE_BUFFERING or now - self._last_buffer_ui >= BUFFER_UI_INTERVAL:
                    self._last_buffer_ui = now
                    self._set_state(STATE_BUFFERING, detail)
                # 还在缓冲说明数据在流进来，把看门狗往后推，避免慢速流被误判为断流
                self._bump_watchdog()

        elif state in ("stopped", "ended", "error"):
            if self._manual_stop or not self._should_play:
                self._set_state(STATE_IDLE, "")
                return
            if state == "stopped" and self._state == STATE_CONNECTING:
                # 每次起流都是先 stop 再 play，会收到一条陈旧的 stopped 事件，
                # 此时还没进入播放状态，忽略它，否则会造成无谓的重连。
                return
            reason = {"stopped": "播放已停止", "ended": "流已结束", "error": "连接失败"}[state]
            self._reconnectRequested.emit(reason)

    def _on_job_started(self) -> None:
        """后台起流任务已开始，此时才武装看门狗（避免排队等待被误判为超时）。"""
        if self._destroyed or not self._should_play or self._manual_stop:
            return
        self._started_at = time.monotonic()
        self._watchdog.start(self._engine.config.connect_timeout * 1000)

    def _schedule_reconnect(self, reason: str) -> None:
        if self._destroyed or not self._should_play or self._manual_stop:
            return
        cfg = self._engine.config
        if not cfg.auto_reconnect:
            self._watchdog.stop()
            self._set_state(STATE_OFFLINE, reason)
            return
        if cfg.max_retries and self._retries >= cfg.max_retries:
            self._watchdog.stop()
            self._set_state(STATE_OFFLINE, f"{reason}（已达最大重试次数）")
            return
        if self._retry_timer.isActive():
            return

        self._retries += 1
        delay = min(cfg.reconnect_interval * (2 ** min(self._retries - 1, 4)), 60)
        total = "∞" if not cfg.max_retries else str(cfg.max_retries)
        log.info(
            "通道 %s %s，%s 秒后第 %s/%s 次重连",
            self.index + 1,
            reason,
            delay,
            self._retries,
            total,
        )
        self._set_state(
            STATE_RECONNECTING, f"{reason}，{delay}s 后第 {self._retries}/{total} 次重连"
        )
        self._retry_timer.start(delay * 1000)

    def _do_reconnect(self) -> None:
        if self._destroyed or not self._should_play or self._manual_stop:
            return
        self._start_media()

    def _on_watchdog(self) -> None:
        """连接超时：还没进入播放状态就重连。"""
        if self._destroyed or not self._should_play or self._manual_stop:
            return
        if self._state == STATE_PLAYING:
            return
        self._reconnectRequested.emit("连接超时")

    def _bump_watchdog(self) -> None:
        """缓冲中时延长看门狗，但总等待时间不超过 connect_timeout 的 3 倍。"""
        if self._destroyed or not self._should_play or self._manual_stop:
            return
        limit_ms = self._engine.config.connect_timeout * 1000
        elapsed_ms = (time.monotonic() - self._started_at) * 1000
        remaining = int(limit_ms * 3 - elapsed_ms)
        if remaining > 0:
            self._watchdog.start(max(remaining, 3000))

    # ------------------------------------------------------------------ #
    #  对外接口
    # ------------------------------------------------------------------ #

    def bind_widget(self, widget) -> None:
        """把 VLC 的视频输出绑定到 Qt 部件的窗口句柄（后台执行）。"""
        self._widget_id = int(widget.winId())
        self._dispatch.post("bind", self._bind_job)

    def _bind_job(self) -> None:
        if self._destroyed or self._widget_id is None:
            return
        try:
            self._player.set_hwnd(self._widget_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("通道 %s 绑定窗口失败: %s", self.index + 1, exc)
        # 让 Qt 收到鼠标/键盘事件，VLC 不再接管
        for setter in ("video_set_mouse_input", "video_set_key_input"):
            try:
                getattr(self._player, setter)(False)
            except Exception:  # noqa: BLE001
                pass

    def play(self, url: str, reset_retries: bool = True) -> None:
        self._url = (url or "").strip()
        if not self._url:
            self.stop()
            return
        self._manual_stop = False
        self._should_play = True
        if reset_retries:
            self._retries = 0
        self._retry_timer.stop()
        self._start_media()

    def _media_options(self) -> List[str]:
        cfg = self._engine.config
        opts = [f":network-caching={cfg.network_caching}"]
        if self._url.lower().startswith("rtsp") and cfg.rtsp_tcp:
            opts.append(":rtsp-tcp")
        if self._recording and self._record_path is not None:
            opts.append(f":sout={self._build_sout()}")
            opts.append(":sout-keep")
        return opts

    def _build_sout(self) -> str:
        """构造「本地显示 + 同时写文件」的 sout 链。

        libvlc 3.x 没有提供录制开关 API，录制只能通过 sout 管线实现；
        代价是开始/停止录制需要重新连接该路流。
        """
        cfg = self._engine.config
        mux = cfg.record_mux if cfg.record_mux in ("ts", "mkv", "mp4") else "ts"
        dst = str(self._record_path).replace("\\", "/")
        return f"#duplicate{{dst=display,dst=std{{access=file,mux={mux},dst={dst}}}}}"

    def _start_media(self) -> None:
        """主线程：立刻给出界面反馈，真正的阻塞操作丢给后台线程。"""
        if self._destroyed:
            return
        self._set_state(STATE_CONNECTING, "正在连接…" if self._retries == 0 else "正在重连…")
        self._started_at = 0.0
        self._watchdog.stop()  # 由 _on_job_started 在任务真正开始时武装
        self._dispatch.post("start", self._start_media_job)

    # --- 以下运行在后台线程 ------------------------------------------- #

    def _start_media_job(self) -> None:
        if self._destroyed:
            return
        try:
            self._player.stop()
        except Exception:  # noqa: BLE001
            pass

        url = self._url
        if not url:
            return

        try:
            media = self._engine.instance.media_new(url)
            for opt in self._media_options():
                media.add_option(opt)
            self._player.set_media(media)
            self._media = media
        except Exception as exc:  # noqa: BLE001
            log.error("通道 %s 创建媒体失败: %s", self.index + 1, exc)
            self._vlcState.emit("error")
            return

        if self._widget_id:
            try:
                self._player.set_hwnd(self._widget_id)
            except Exception:  # noqa: BLE001
                pass

        try:
            self._player.play()
        except Exception as exc:  # noqa: BLE001
            log.error("通道 %s 播放失败: %s", self.index + 1, exc)
            self._vlcState.emit("error")
            return

        self._apply_audio()
        self._jobStarted.emit()

    def stop(self) -> None:
        self._manual_stop = True
        self._should_play = False
        self._retries = 0
        self._watchdog.stop()
        self._retry_timer.stop()
        if self._recording:
            self.set_recording(False, restart=False)
        self._set_state(STATE_IDLE, "")
        self._dispatch.post("stop", self._stop_job)

    def _stop_job(self) -> None:
        try:
            self._player.stop()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #

    def apply_config(self, volume: int, muted: bool, fit: str) -> None:
        """只更新参数并把实际生效丢到后台线程。

        为什么不能在 UI 线程直接调：
            ``libvlc_video_set_aspect_ratio()`` / ``video_set_scale()`` /
            ``audio_set_volume()`` 内部都要先 ``libvlc_get_input_thread()``，
            也就是去抢 libvlc 的 input 锁。只要有任何一路的 ``stop()`` 正在
            后台执行（车载 NVR 断流时一次可达 3 秒），主线程就会排队等锁 →
            点完「配置 → 确定」界面直接卡死十几秒。实测堆栈见 README。
        """
        self._volume = volume
        self._muted = muted
        self._fit = fit
        self._dispatch.post("config", self._apply_config_job)

    def _apply_config_job(self) -> None:
        self._apply_audio()
        self._apply_fit()

    def _apply_audio(self) -> None:
        if self._destroyed:
            return
        try:
            self._player.audio_set_mute(bool(getattr(self, "_muted", True)))
            self._player.audio_set_volume(int(getattr(self, "_volume", 80)))
        except Exception:  # noqa: BLE001
            pass

    def _apply_fit(self) -> None:
        """恢复「保持比例」；拉伸模式由 :meth:`set_stretch` 按画面尺寸动态设置。"""
        if self._destroyed:
            return
        if getattr(self, "_fit", "keep") == "stretch":
            return
        try:
            self._player.video_set_aspect_ratio(None)
            self._player.video_set_scale(0)
        except Exception:  # noqa: BLE001
            pass

    def set_stretch(self, width: int, height: int) -> None:
        """拉伸铺满：把显示宽高比强制设为画面区域的宽高比。

        同样会抢 input 锁，所以也丢到后台；窗口拖动时会被高频调用，
        这里做「合并投递 + 执行到最新值为止」，避免把队列刷爆。
        """
        if self._destroyed:
            return
        self._stretch_target = (int(width), int(height))
        if self._stretch_pending:
            return
        self._stretch_pending = True
        self._dispatch.post("stretch", self._apply_stretch_job)

    def _apply_stretch_job(self) -> None:
        try:
            while True:
                target = self._stretch_target
                self._apply_stretch_now(target)
                if target == self._stretch_target:
                    break
        finally:
            self._stretch_pending = False

    def _apply_stretch_now(self, target: tuple) -> None:
        if self._destroyed:
            return
        width, height = target
        try:
            if getattr(self, "_fit", "keep") == "stretch" and width > 0 and height > 0:
                self._player.video_set_aspect_ratio(f"{width}:{height}")
            else:
                self._player.video_set_aspect_ratio(None)
        except Exception:  # noqa: BLE001
            pass

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._dispatch.post("audio", self._apply_audio)

    def set_volume(self, volume: int) -> None:
        self._volume = int(volume)
        self._dispatch.post("audio", self._apply_audio)

    # ------------------------------------------------------------------ #

    def take_snapshot(self, path: Path) -> None:
        """截图也走后台：``video_take_snapshot`` 同样要先抢 input 锁。"""
        if self._destroyed:
            return
        self._dispatch.post("snapshot", lambda: self._snapshot_job(path))

    def _snapshot_job(self, path: Path) -> None:
        if self._destroyed:
            self.snapshotDone.emit(self.index, False, str(path))
            return
        ok = False
        try:
            ok = self._player.video_take_snapshot(0, str(path), 0, 0) == 0
        except Exception as exc:  # noqa: BLE001
            log.warning("通道 %s 截图失败: %s", self.index + 1, exc)
        if not ok:
            log.warning("通道 %s 截图失败（可能没有视频输出）", self.index + 1)
        self.snapshotDone.emit(self.index, ok, str(path))

    # ---------------------------------------------------------------- #
    #  录制
    # ---------------------------------------------------------------- #

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def record_path(self) -> Optional[Path]:
        return self._record_path

    def set_record_alias(self, alias: str, stamp: str) -> None:
        self._record_alias = alias or "record"
        self._record_stamp = stamp or ""

    def _next_record_path(self) -> Path:
        cfg = self._engine.config
        mux = cfg.record_mux if cfg.record_mux in ("ts", "mkv", "mp4") else "ts"
        alias = self._record_alias or f"channel{self.index + 1}"
        stamp = self._record_stamp or datetime.now().strftime("_%Y%m%d_%H%M%S")
        target = cfg.record_dir_path() / f"{alias}{stamp}.{mux}"
        n = 1
        while target.exists():
            target = cfg.record_dir_path() / f"{alias}{stamp}({n}).{mux}"
            n += 1
        return target

    def set_recording(self, on: bool, restart: bool = True) -> bool:
        """开始/停止录制。

        因为 libvlc 3.x 只能通过 sout 录制，切换录制状态需要重新连接该路流；
        未在播放时只记录状态，下次播放自动带上 sout。
        """
        if self._destroyed:
            return False
        on = bool(on)
        if on == self._recording:
            return True

        if on:
            self._record_path = self._next_record_path()
        self._recording = on

        live = self._should_play and not self._manual_stop and bool(self._url)
        if restart and live:
            self._start_media()

        self._emit_status()
        return True

    # ------------------------------------------------------------------ #

    @property
    def state(self) -> str:
        return self._state

    def _set_state(self, state: str, detail: str = "") -> None:
        if self._state == state and self._detail == detail:
            return
        self._state = state
        self._detail = detail
        log.debug("通道 %s 状态 -> %s %s", self.index + 1, state, detail)
        self._emit_status()

    def _emit_status(self) -> None:
        detail = self._detail
        if self._recording:
            detail = (detail + " · 录制中").strip(" ·")
        self.statusChanged.emit(self.index, self._state, detail)

    def status_text(self) -> str:
        text = STATE_TEXT.get(self._state, self._state)
        if self._detail:
            text = f"{text} · {self._detail}"
        return text

    # ------------------------------------------------------------------ #

    def destroy(self) -> None:
        self._destroyed = True
        self._watchdog.stop()
        self._retry_timer.stop()
        self._release_events()
        self._dispatch.post("release", self._release_job)

    def _release_job(self) -> None:
        try:
            self._player.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._player.release()
        except Exception:  # noqa: BLE001
            pass
        self._media = None
