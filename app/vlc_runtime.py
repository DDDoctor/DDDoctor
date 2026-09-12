"""定位并初始化 VLC 运行库（libvlc.dll / libvlccore.dll / plugins）。"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path
from typing import Iterator, Optional

from .paths import app_dir, is_frozen, resource_dir

log = logging.getLogger(__name__)

#: 环境变量可用于强制指定 VLC 运行库目录
ENV_OVERRIDE = "MULTIVIEW_VLC_DIR"

_REQUIRED = ("libvlc.dll", "libvlccore.dll")

_vlc_dir: Optional[Path] = None
_preloaded = False


def _candidates() -> Iterator[Path]:
    override = os.environ.get(ENV_OVERRIDE) or os.environ.get("VLC_HOME")
    if override:
        yield Path(override)
    # 打包后：_MEIPASS/vlc
    yield resource_dir() / "vlc"
    yield resource_dir() / "vendor" / "vlc"
    # 源码运行 / 绿色目录
    yield app_dir() / "vlc"
    yield app_dir() / "vendor" / "vlc"
    # 系统安装的 VLC
    for base in (r"C:\Program Files\VideoLAN\VLC", r"C:\Program Files (x86)\VideoLAN\VLC"):
        yield Path(base)


def find_vlc_dir() -> Optional[Path]:
    """返回第一个包含完整 VLC 运行库的目录。"""
    global _vlc_dir
    if _vlc_dir is not None:
        return _vlc_dir
    for cand in _candidates():
        try:
            if cand.is_dir() and all((cand / f).is_file() for f in _REQUIRED):
                _vlc_dir = cand.resolve()
                return _vlc_dir
        except OSError:
            continue
    return None


def prepare() -> Optional[Path]:
    """把 VLC 运行库接入当前进程的 DLL 搜索路径，必须在 ``import vlc`` 前调用。"""
    global _preloaded
    d = find_vlc_dir()
    if d is None:
        return None

    # 1) 让 libvlc.dll 依赖的同目录 DLL（libvlccore.dll 等）能被找到
    try:
        os.add_dll_directory(str(d))
    except (AttributeError, OSError) as exc:  # pragma: no cover
        log.debug("add_dll_directory 失败: %s", exc)

    os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")

    plugins = d / "plugins"
    if plugins.is_dir():
        os.environ["VLC_PLUGIN_PATH"] = str(plugins)

    # python-vlc 读取这两个变量定位库文件
    os.environ.setdefault("PYTHON_VLC_MODULE_PATH", str(d))
    os.environ["PYTHON_VLC_LIB_PATH"] = str(d / "libvlc.dll")

    # 2) 主动按绝对路径预加载，确保即使 PATH 未生效也能加载主库
    if not _preloaded:
        try:
            ctypes.CDLL(str(d / "libvlccore.dll"))
        except OSError as exc:  # pragma: no cover
            log.debug("预加载 libvlccore.dll 失败: %s", exc)
        try:
            ctypes.CDLL(str(d / "libvlc.dll"))
            _preloaded = True
        except OSError as exc:  # pragma: no cover
            log.warning("预加载 libvlc.dll 失败: %s", exc)

    log.info("VLC 运行库目录: %s", d)
    return d


def vlc_dir() -> Optional[Path]:
    return find_vlc_dir()


def describe() -> str:
    d = find_vlc_dir()
    if d is None:
        return "未找到 VLC 运行库"
    origin = "内置" if is_frozen() or "vendor" in str(d) or d.parent == app_dir() else "系统安装"
    try:
        import vlc  # noqa: PLC0415

        return f"VLC {vlc.libvlc_get_version().decode('ascii', 'replace')} ({origin})"
    except Exception:  # noqa: BLE001
        return f"VLC 运行库: {d}"
