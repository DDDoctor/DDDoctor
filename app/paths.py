"""路径解析：兼容源码运行与 PyInstaller 打包后的运行环境。"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from .constants import APP_NAME


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


@lru_cache(maxsize=1)
def resource_dir() -> Path:
    """只读资源目录（打包后为解包临时目录 _MEIPASS）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def app_dir() -> Path:
    """程序所在目录（打包后为 exe 所在目录）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _app_dir_writable() -> bool:
    try:
        probe = app_dir() / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """配置 / 日志 / 截图的存放目录。优先程序目录，不可写时退回 %APPDATA%。"""
    if _app_dir_writable():
        return app_dir()
    fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def config_path() -> Path:
    return data_dir() / "config.json"


def log_path() -> Path:
    return data_dir() / "multiview.log"


def default_snapshot_dir() -> Path:
    return data_dir() / "snapshots"


def default_record_dir() -> Path:
    return data_dir() / "recordings"
