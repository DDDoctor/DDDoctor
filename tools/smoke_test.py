"""冒烟测试：不依赖界面，直接验证 VLC 运行库、播放、截图、sout 录制。

    .venv\\Scripts\\python.exe tools\\smoke_test.py [流地址]

默认使用公开的 HLS 测试流（H.264 + AAC，可被 TS 封装，适合验证录制）。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vlc_runtime  # noqa: E402

VLC = vlc_runtime.prepare()
print(f"[1] VLC 运行库: {VLC}", flush=True)

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import vlc  # noqa: E402

from app.config import AppConfig  # noqa: E402
from app.dispatch import get_pool  # noqa: E402
from app.player import ChannelPlayer, VlcEngine  # noqa: E402

DEFAULT_URL = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
URL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

WORK = ROOT / "build_cache" / "smoke"

cfg = AppConfig()
# 用「相对程序目录」的写法，验证生产环境下目录解析是否正确
cfg.record_dir = "build_cache/smoke/rec"
cfg.snapshot_dir = "build_cache/smoke/snap"
cfg.record_mux = "ts"
cfg.network_caching = 1000
cfg.connect_timeout = 30
cfg.normalize()

REC = cfg.record_dir_path()
SNAP = cfg.snapshot_dir_path()
for d in (REC, SNAP):
    d.mkdir(parents=True, exist_ok=True)
print(f"[0] 相对路径 'recordings' 解析结果: {REC}", flush=True)
print(f"    相对路径 'snapshots'  解析结果: {SNAP}", flush=True)

app = QApplication(sys.argv)
engine = VlcEngine(cfg)
print(f"[2] libvlc 版本: {vlc.libvlc_get_version().decode()}", flush=True)

window = QWidget()
window.resize(720, 405)
window.move(80, 80)
window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
window.show()
window.raise_()
window.activateWindow()

player = ChannelPlayer(0, engine, get_pool().for_index(0))
player.bind_widget(window)
player.apply_config(0, True, "keep")

states: list[str] = []
player.statusChanged.connect(lambda i, s, d: states.append(s))
player.play(URL)

results: dict[str, object] = {"record_files": []}
phase = {"n": 0}
deadline = {"t": 0}

POLL = QTimer()
POLL.setInterval(1000)


def snapshot() -> None:
    n = len([k for k in results if k.startswith("snapshot")])
    target = SNAP / f"smoke_{n}.png"
    # 截图已改为异步（避免抢 libvlc 的 input 锁卡住界面），结果通过信号回调
    player.take_snapshot(target)
    app.processEvents()
    # 结果在 snapshotDone 里落库，这里先占位
    results.setdefault(f"snapshot{n}", (None, 0))
    print(f"[4] 截图#{n} 已提交（异步）", flush=True)


def on_snapshot_done(index: int, ok: bool, path: str) -> None:
    p = Path(path)
    size = p.stat().st_size if p.is_file() else 0
    for key in list(results):
        if key.startswith("snapshot") and results[key] == (None, 0):
            results[key] = (ok, size)
            print(
                f"    截图完成 -> 成功={ok}, 文件={p.name}, {size} 字节, "
                f"has_vout={player._player.has_vout()}, 录制中={player.recording}",
                flush=True,
            )
            return


player.snapshotDone.connect(on_snapshot_done)


def start_record() -> None:
    player.set_record_alias("smoke", "_rec")
    player.set_recording(True)
    print(f"[5] 开始录制 -> {player.record_path}", flush=True)


def grab(tag: str) -> None:
    """抓取整个桌面，用来确认 VLC 的视频画面是否真的渲染出来了。"""
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    shot = screen.grabWindow(0)
    target = SNAP / f"desktop_{tag}.png"
    shot.save(str(target))
    print(f"[8] 桌面截图({tag}) -> {target.name}  {target.stat().st_size} 字节", flush=True)


def stop_record() -> None:
    player.set_recording(False, restart=False)
    files = sorted(p for p in REC.iterdir() if p.is_file())
    results["record_files"] = [(p.name, p.stat().st_size) for p in files]
    for name, size in results["record_files"]:
        print(f"[6] 录制文件: {name}  {size / 1024:.0f} KB", flush=True)


SEQUENCE = [
    (5, snapshot),                            # 播放稳定后先截图
    (7, start_record),                        # 再开启录制（会重连一次）
    (13, snapshot),                           # 录制过程中再截一张，验证 sout 下仍有 vout
    (15, lambda: grab("during_record")),      # 抓桌面确认画面可见
    (26, stop_record),                        # 录 15 秒后停止
    (29, lambda: grab("after_record")),
]


def tick() -> None:
    deadline["t"] += 1
    if deadline["t"] > 90:
        print("[!] 总超时", flush=True)
        finish()
        return

    while phase["n"] < len(SEQUENCE) and deadline["t"] >= SEQUENCE[phase["n"]][0]:
        SEQUENCE[phase["n"]][1]()
        phase["n"] += 1

    if phase["n"] >= len(SEQUENCE):
        finish()


def finish() -> None:
    POLL.stop()
    unique: list[str] = []
    for s in states:
        if not unique or unique[-1] != s:
            unique.append(s)
    print(f"[7] 状态流转: {' -> '.join(unique)}", flush=True)
    player.destroy()
    engine.release()
    app.quit()


POLL.timeout.connect(tick)
POLL.start()
QTimer.singleShot(0, lambda: print(f"[3] 播放: {URL}", flush=True))
app.exec()

snaps = [v for k, v in sorted(results.items()) if k.startswith("snapshot")]
files = results["record_files"]
ok_rec = any(size > 4096 for _, size in files) if files else False
first_snap_ok = bool(snaps) and bool(snaps[0][0]) and snaps[0][1] > 0
print()
print(f"截图测试(未录制): {'PASS' if first_snap_ok else 'FAIL'}")
if len(snaps) > 1:
    during = bool(snaps[1][0]) and snaps[1][1] > 0
    print(f"截图测试(录制中): {'PASS' if during else 'FAIL —— sout 模式下 VLC 不提供可截图的 vout（已知限制）'}")
print(f"录制测试: {'PASS' if ok_rec else 'FAIL'}")
overall = first_snap_ok and ok_rec
print(f"\n总体：{'PASS' if overall else 'FAIL'}")
sys.exit(0 if overall else 1)
