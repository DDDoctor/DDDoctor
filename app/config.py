"""配置数据模型与 JSON 读写。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List

from .constants import (
    MAX_CHANNELS,
    FIT_KEEP,
    STATE_IDLE,
)
from .paths import app_dir, config_path

log = logging.getLogger(__name__)

#: 相对程序目录的默认子目录（用相对路径，换版本/换目录后不会写回旧位置）
DEFAULT_SNAPSHOT_REL = "snapshots"
DEFAULT_RECORD_REL = "recordings"


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def migrate_dir(value: Any, default_rel: str) -> str:
    """把目录设置规范化为「相对程序目录」或「用户自定义的绝对路径」。

    历史问题：早期版本把默认目录存成了绝对路径，于是换了版本目录之后，
    录制仍然写回旧版本目录（旧目录被删掉还会被重新创建出来）。
    这里把指向 MultiView 安装目录的绝对路径改回相对路径。
    """
    text = str(value or "").strip()
    if not text:
        return default_rel
    p = Path(text).expanduser()
    if not p.is_absolute():
        return text
    parts = [q.lower() for q in p.parts]
    if any(q == "multiview" or q.startswith("multiview-") for q in parts):
        return default_rel
    return text


def resolve_dir(value: Any, default_rel: str) -> Path:
    """相对路径按程序目录解析；绝对路径原样使用。"""
    text = str(value or "").strip() or default_rel
    p = Path(text).expanduser()
    if not p.is_absolute():
        p = app_dir() / p
    return p


def store_dir(path_like: Any, default_rel: str) -> str:
    """保存时：位于程序目录内就存成相对路径，否则存绝对路径。"""
    text = str(path_like or "").strip()
    if not text:
        return default_rel
    p = Path(text).expanduser()
    if not p.is_absolute():
        return text
    try:
        rel = p.resolve().relative_to(app_dir().resolve())
        rel_text = str(rel)
        return default_rel if rel_text in ("", ".") else rel_text
    except (ValueError, OSError):
        return text


@dataclass
class ChannelConfig:
    """单个通道的配置。"""

    enabled: bool = False
    name: str = ""
    url: str = ""
    volume: int = 80          # 0 - 100
    muted: bool = True
    fit: str = ""             # 空 = 跟随全局

    def display_name(self, index: int) -> str:
        return self.name.strip() or f"通道 {index + 1}"

    def active(self) -> bool:
        """启用且填写了地址，才参与画面网格。"""
        return self.enabled and bool(self.url.strip())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "ChannelConfig":
        if not isinstance(data, dict):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            name=str(data.get("name", "") or ""),
            url=str(data.get("url", "") or "").strip(),
            volume=_clamp_int(data.get("volume", 80), 0, 200, 80),
            muted=bool(data.get("muted", True)),
            fit=str(data.get("fit", "") or ""),
        )


@dataclass
class AppConfig:
    """应用全局配置。"""

    channels: List[ChannelConfig] = field(default_factory=list)

    # 播放参数
    network_caching: int = 300        # 毫秒
    rtsp_tcp: bool = True
    hw_decode: str = "any"
    fit: str = FIT_KEEP

    # 重连
    auto_reconnect: bool = True
    reconnect_interval: int = 3       # 秒（基准间隔，失败后指数退避）
    max_retries: int = 0              # 0 = 无限
    connect_timeout: int = 15         # 秒

    # 目录与录制
    snapshot_dir: str = ""
    record_dir: str = ""
    record_mux: str = "ts"

    # 界面
    autoplay_on_start: bool = True
    show_header: bool = True
    fill_last_row: bool = False
    zoom_fullscreen: bool = True   # 双击画面 = 单画面全屏

    # 其它
    version: int = 1

    # ------------------------------------------------------------------ #

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        """补齐通道数量并做范围校正（配置被手工编辑后也能安全加载）。"""
        if not isinstance(self.channels, list):
            self.channels = []
        fixed: List[ChannelConfig] = []
        for i in range(MAX_CHANNELS):
            raw = self.channels[i] if i < len(self.channels) else None
            ch = raw if isinstance(raw, ChannelConfig) else ChannelConfig.from_dict(raw)
            ch.volume = _clamp_int(ch.volume, 0, 200, 80)
            if ch.fit not in ("", FIT_KEEP, "stretch"):
                ch.fit = ""
            fixed.append(ch)
        self.channels = fixed

        self.network_caching = _clamp_int(self.network_caching, 0, 60000, 300)
        self.reconnect_interval = _clamp_int(self.reconnect_interval, 1, 120, 3)
        self.max_retries = _clamp_int(self.max_retries, 0, 9999, 0)
        self.connect_timeout = _clamp_int(self.connect_timeout, 3, 300, 15)
        if self.hw_decode not in ("any", "d3d11va", "dxva2", "none"):
            self.hw_decode = "any"
        if self.fit not in ("keep", "stretch"):
            self.fit = FIT_KEEP
        if self.record_mux not in ("ts", "mkv", "mp4"):
            self.record_mux = "ts"

        if not self.snapshot_dir:
            self.snapshot_dir = DEFAULT_SNAPSHOT_REL
        if not self.record_dir:
            self.record_dir = DEFAULT_RECORD_REL
        self.snapshot_dir = migrate_dir(self.snapshot_dir, DEFAULT_SNAPSHOT_REL)
        self.record_dir = migrate_dir(self.record_dir, DEFAULT_RECORD_REL)

    # ------------------------------------------------------------------ #

    def active_channels(self) -> List[int]:
        """返回参与网格显示的通道序号（启用且地址非空）。"""
        return [i for i, ch in enumerate(self.channels) if ch.active()]

    def effective_fit(self, index: int) -> str:
        ch = self.channels[index]
        return ch.fit or self.fit

    def snapshot_dir_path(self) -> Path:
        p = resolve_dir(self.snapshot_dir, DEFAULT_SNAPSHOT_REL)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def record_dir_path(self) -> Path:
        p = resolve_dir(self.record_dir, DEFAULT_RECORD_REL)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def snapshot_dir_display(self) -> str:
        return str(resolve_dir(self.snapshot_dir, DEFAULT_SNAPSHOT_REL))

    def record_dir_display(self) -> str:
        return str(resolve_dir(self.record_dir, DEFAULT_RECORD_REL))

    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        data = asdict(self)
        data["channels"] = [ch.to_dict() for ch in self.channels]
        return data

    @classmethod
    def from_dict(cls, data: Any) -> "AppConfig":
        if not isinstance(data, dict):
            return cls()
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in known and k != "channels"}
        cfg = cls(channels=[ChannelConfig.from_dict(c) for c in (data.get("channels") or [])], **kwargs)
        cfg.normalize()
        return cfg

    # ------------------------------------------------------------------ #

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path else config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
        tmp.replace(target)
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        target = Path(path) if path else config_path()
        if not target.is_file():
            return cls()
        try:
            # utf-8-sig：兼容手工用记事本编辑后带 BOM 的配置文件
            with open(target, "r", encoding="utf-8-sig") as fh:
                return cls.from_dict(json.load(fh))
        except Exception as exc:  # noqa: BLE001
            log.warning("读取配置失败 %s: %s", target, exc)
            return cls()

    def clone(self) -> "AppConfig":
        return AppConfig.from_dict(self.to_dict())


def demo_config() -> AppConfig:
    """首次运行时的示例配置：桌面捕获 + 两路公开测试流，保证开箱即可看到画面。"""
    cfg = AppConfig()
    samples = [
        ("屏幕捕获(测试)", "screen://"),
        ("测试流 HLS", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
        ("测试流 MP4", "https://media.w3.org/2010/05/sintel/trailer.mp4"),
    ]
    for i, (name, url) in enumerate(samples):
        ch = cfg.channels[i]
        ch.enabled = True
        ch.name = name
        ch.url = url
        ch.muted = i != 0
        ch.volume = 80
    cfg.show_header = True
    return cfg
