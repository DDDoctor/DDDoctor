"""用 VLC verbose 日志确认音频输出是否真的建立起来了。

    .venv\\Scripts\\python.exe tools\\audio_verbose.py --url <流地址>
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

vlc_runtime.prepare()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import vlc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="rtsp://192.168.1.10:554/Streaming/Channels/1")
ap.add_argument("--wait", type=float, default=14.0)
args = ap.parse_args()

app = QApplication(sys.argv)

# 注意：故意不加 --quiet，让 VLC 把音频相关的日志打到 stderr
inst = vlc.Instance(
    [
        "--intf=dummy",
        "--no-video-title-show",
        "--verbose=2",
        "--rtsp-tcp",
        "--network-caching=800",
    ]
)
mp = inst.media_player_new()
w = QWidget()
w.resize(320, 180)
w.show()
mp.set_hwnd(int(w.winId()))
media = inst.media_new(args.url)
mp.set_media(media)
mp.audio_set_mute(False)
mp.audio_set_volume(80)
mp.play()
print(f"VERBOSE 开始播放 {args.url}", flush=True)


def finish() -> None:
    try:
        print(f"音轨数={mp.audio_get_track_count()} 音量={mp.audio_get_volume()} 静音={mp.audio_get_mute()}")
    except Exception as exc:  # noqa: BLE001
        print("查询失败", exc)
    mp.stop()
    mp.release()
    inst.release()
    app.quit()


QTimer.singleShot(int(args.wait * 1000), finish)
app.exec()
time.sleep(0.3)
sys.exit(0)
