"""逐个试探 RTSP 地址是否可用（判断设备的通道号写法）。

    .venv\\Scripts\\python.exe tools\\url_probe.py --host 192.168.1.10
    .venv\\Scripts\\python.exe tools\\url_probe.py --urls a,b,c
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

vlc_runtime.prepare()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import vlc  # noqa: E402


def candidates(host: str, port: int = 554) -> list[str]:
    base = f"rtsp://{host}:{port}"
    urls: list[str] = []
    # 常见 NVR/DVR 通道号写法
    for n in range(1, 12):
        urls.append(f"{base}/Streaming/Channels/{n}")
    for n in range(1, 12):
        urls.append(f"{base}/Streaming/Channels/{n}01")
    urls.append(f"{base}/Streaming/Channels/101")
    urls.append(f"{base}/Streaming/Channels/102")
    urls.append(f"{base}/cam/realmonitor?channel=1&subtype=0")
    urls.append(f"{base}/Streaming/Channels/1?transportmode=unicast")
    urls.append(f"{base}/h264/ch1/main/av_stream")
    urls.append(f"{base}/h264/ch2/main/av_stream")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.1.10")
    ap.add_argument("--port", type=int, default=554)
    ap.add_argument("--urls", default="")
    ap.add_argument("--timeout", type=float, default=12.0)
    args = ap.parse_args()

    urls = (
        [u.strip() for u in args.urls.split(",") if u.strip()]
        if args.urls
        else candidates(args.host, args.port)
    )

    app = QApplication(sys.argv)
    inst = vlc.Instance(
        ["--intf=dummy", "--no-video-title-show", "--quiet", "--rtsp-tcp", "--network-caching=500"]
    )
    holder = QWidget()
    holder.resize(320, 180)
    holder.show()

    results: list[tuple[str, bool, str]] = []
    queue = list(urls)

    def next_url() -> None:
        if not queue:
            finish()
            return
        url = queue.pop(0)
        state = {"url": url, "done": False}

        mp = inst.media_player_new()
        mp.set_hwnd(int(holder.winId()))
        media = inst.media_new(url)
        mp.set_media(media)
        mp.play()

        def check() -> None:
            if state["done"]:
                return
            state["done"] = True
            st = str(mp.get_state())
            w, h = mp.video_get_size(0)
            ok = st == "State.Playing" and w > 0
            info = f"{st}  {w}x{h}" if w else st
            results.append((url, ok, info))
            print(f"  {'可用 ' if ok else '不可用'} {url}   [{info}]", flush=True)
            mp.stop()
            mp.release()
            QTimer.singleShot(1500, next_url)

        QTimer.singleShot(int(args.timeout * 1000), check)

    def finish() -> None:
        print()
        good = [u for u, ok, _ in results if ok]
        print(f"共测试 {len(results)} 个地址，可用 {len(good)} 个：")
        for u in good:
            print(f"  ✅ {u}")
        if not good:
            print("  （没有可用地址，请确认账号密码/端口/编码格式）")
        inst.release()
        app.quit()

    QTimer.singleShot(300, next_url)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
