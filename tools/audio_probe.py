"""诊断音频链路：某路流到底有没有音轨、音量/静音状态是否正常。

    .venv\\Scripts\\python.exe tools\\audio_probe.py --url <流地址>
    .venv\\Scripts\\python.exe tools\\audio_probe.py            # 用公开测试流
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

from app.config import AppConfig  # noqa: E402
from app.dispatch import get_pool  # noqa: E402
from app.player import ChannelPlayer, VlcEngine  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8")
ap.add_argument("--wait", type=float, default=15.0)
ap.add_argument("--volume", type=int, default=80)
ap.add_argument("--unmute", action="store_true", default=True)
args = ap.parse_args()

cfg = AppConfig()
cfg.network_caching = 800
cfg.connect_timeout = 40
cfg.normalize()

app = QApplication(sys.argv)
engine = VlcEngine(cfg)
window = QWidget()
window.resize(320, 180)
window.show()
player = ChannelPlayer(0, engine, get_pool().for_index(0))
player.bind_widget(window)
player.apply_config(args.volume, not args.unmute, "keep")
player.play(args.url)
print(f"播放: {args.url}")


def report() -> None:
    p = player._player  # noqa: SLF001
    print()
    print("=== 音频诊断 ===")
    print(f"  播放状态        : {player.state}")
    try:
        print(f"  音轨数量        : {p.audio_get_track_count()}")
        for desc in p.audio_get_track_description() or []:
            try:
                print(f"      id={desc[0]}  name={desc[1].decode('utf-8', 'replace')}")
            except Exception:  # noqa: BLE001
                print(f"      {desc}")
        print(f"  当前音轨        : {p.audio_get_track()}")
        print(f"  实际音量        : {p.audio_get_volume()}")
        print(f"  实际静音        : {p.audio_get_mute()}")
        print(f"  音频输出设备    : {p.audio_output_device_get()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  查询失败: {exc}")

    n = p.audio_get_track_count()
    print()
    if n <= 0:
        print("结论：这条流【没有音轨】—— 播放器再怎么设置也不会有声音。")
        print("      摄像头/NVR 的主码流通常不含音频，需要确认设备端是否开启了麦克风/音频编码。")
    else:
        print(f"结论：流里有 {n} 条音轨。若仍听不到声音，请检查：")
        print("      1) 系统音量 / 默认播放设备是否正确")
        print("      2) 该通道在配置里是否被勾了「静音」")
        print("      3) 全局静音按钮是否被按下")
    player.destroy()
    app.quit()


QTimer.singleShot(int(args.wait * 1000), report)
app.exec()
