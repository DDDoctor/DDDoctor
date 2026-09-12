"""生成压力测试配置：N 路「连不上」的 RTSP，用来复现多通道卡死问题。

    .venv\\Scripts\\python.exe tools\\stress_config.py --channels 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import AppConfig  # noqa: E402

#: TEST-NET-1，保证不可路由 —— 用来模拟「摄像头连不上」的场景
DEAD = "rtsp://192.0.2.1:554/Streaming/Channels/101?transportmode=unicast&profile=Profile_1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", type=int, default=8)
    ap.add_argument("--out", default=str(ROOT / "config.json"))
    ap.add_argument("--url", default=DEAD)
    ap.add_argument("--mixed", action="store_true", help="一半可用流 + 一半死地址")
    args = ap.parse_args()

    cfg = AppConfig()
    cfg.connect_timeout = 15
    cfg.network_caching = 300
    n = max(1, min(18, args.channels))
    for i in range(n):
        ch = cfg.channels[i]
        ch.enabled = True
        ch.name = f"压力通道 {i + 1}"
        if args.mixed and i % 2 == 0:
            ch.url = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
            ch.name = f"可用流 {i + 1}"
        else:
            ch.url = args.url
        ch.muted = True
        ch.volume = 80
    cfg.autoplay_on_start = True
    cfg.normalize()
    target = Path(args.out)
    cfg.save(target)
    print(f"已生成 {n} 路压力配置 -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
