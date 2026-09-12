"""查看配置文件里的通道、音量、静音和目录设置。

    .venv\\Scripts\\python.exe tools\\inspect_config.py [config.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT = "config.user-backup.json"


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    if not target.is_file():
        print(f"找不到配置文件: {target}")
        return 1
    data = json.loads(target.read_text(encoding="utf-8-sig"))

    print(f"=== {target} ===")
    print("--- 目录 / 录制 ---")
    for key in ("snapshot_dir", "record_dir", "record_mux", "record_mux"):
        if key in data:
            print(f"  {key:14} = {data[key]}")
    print("--- 播放参数 ---")
    for key in (
        "network_caching",
        "rtsp_tcp",
        "hw_decode",
        "fit",
        "auto_reconnect",
        "reconnect_interval",
        "max_retries",
        "connect_timeout",
        "autoplay_on_start",
    ):
        if key in data:
            print(f"  {key:18} = {data[key]}")

    print("--- 通道（启用且有地址的）---")
    muted_count = 0
    for i, ch in enumerate(data.get("channels", [])):
        if ch.get("enabled") and ch.get("url"):
            if ch.get("muted"):
                muted_count += 1
            print(
                f"  {i + 1:2d}  {ch.get('name', ''):<24} "
                f"vol={ch.get('volume'):<4} muted={ch.get('muted')}  {ch.get('url', '')[:52]}"
            )
    print(f"  → 其中静音的通道数: {muted_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
