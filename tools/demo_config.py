"""生成一份演示/测试用配置，方便在没有内网摄像头时快速验证软件。

    .venv\\Scripts\\python.exe tools\\demo_config.py                 # 写到 config.json（会覆盖！）
    .venv\\Scripts\\python.exe tools\\demo_config.py --out demo.json --channels 6
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import AppConfig  # noqa: E402
from app.paths import config_path  # noqa: E402

SOURCES = [
    ("测试流 HLS 1", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 2", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 3", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 4", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 MP4", "https://media.w3.org/2010/05/sintel/trailer.mp4"),
    ("测试流 HLS 5", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 6", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 7", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 8", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 9", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 10", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 11", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("测试流 HLS 12", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"),
    ("屏幕捕获", "screen://"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(config_path()))
    ap.add_argument("--channels", type=int, default=6)
    ap.add_argument("--unmute-first", action="store_true", default=True)
    args = ap.parse_args()

    cfg = AppConfig()
    n = max(1, min(len(SOURCES), args.channels))
    for i in range(n):
        name, url = SOURCES[i]
        ch = cfg.channels[i]
        ch.enabled = True
        ch.name = name
        ch.url = url
        ch.muted = i != 0
        ch.volume = 80
    cfg.autoplay_on_start = True
    cfg.normalize()

    target = Path(args.out)
    cfg.save(target)
    print(f"已写入 {n} 路演示通道 -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
