"""把可能阻塞的 libvlc 调用挪到后台线程执行。

为什么需要它
------------
libvlc 3.x 里有一大批**同步阻塞**的接口：

* ``stop()`` / ``set_media()`` / ``play()`` / ``release()`` —— 要等输入线程结束；
* ``video_set_aspect_ratio()`` / ``video_set_scale()`` / ``audio_set_*()`` /
  ``video_take_snapshot()`` —— 内部都要先 ``libvlc_get_input_thread()``，
  也就是去抢 libvlc 的 **input 锁**。

只要后台有任意一路的 ``stop()`` 在跑（车载 NVR 断流时单次可达 3 秒），
这些调用在 UI 线程上就会排队等锁 —— 点一下「配置 → 确定」卡死十几秒就是这么来的。

方案：每个工作线程是一个 **FIFO 队列**，同一通道的播放操作按提交顺序执行；
同时用多个工作线程，保证某一路卡住不会拖累其它通道。

为什么不用 QThread
------------------
实测：QThread 对象在解释器退出时被析构、而线程还在跑，Qt 会 ``qFatal`` ——
进程迟迟退不掉（关闭要 9 秒）并留下卡在内核态的僵尸进程。
改用**普通 Python 守护线程 + queue.Queue**：没有 Qt 对象生命周期问题，
解释器不会等待守护线程，关窗口进程立刻退出。
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, List, Optional

log = logging.getLogger(__name__)

_Job = "tuple[str, Optional[Callable[[], None]]]"


class VlcDispatcher:
    """一个串行执行 libvlc 阻塞调用的守护线程。"""

    def __init__(self, name: str = "vlc-worker") -> None:
        self._queue: "queue.Queue[_Job]" = queue.Queue()
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            label, fn = self._queue.get()
            if fn is None:  # 退出哨兵
                return
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("后台 VLC 操作失败: %s", label)

    def post(self, label: str, fn: Callable[[], None]) -> None:
        """把作业排到队列尾部（立即返回，不阻塞调用线程）。"""
        self._queue.put((label, fn))

    def begin_shutdown(self) -> threading.Event:
        """投递一个屏障作业，返回「排在前面的作业都已跑完」的事件。"""
        done = threading.Event()
        self._queue.put(("barrier", done.set))
        return done

    def request_quit(self) -> None:
        """投递退出哨兵。线程是守护线程，进程退出时系统会直接回收。"""
        self._queue.put(("quit", None))


class VlcDispatcherPool:
    """按通道序号固定分派到某个工作线程。

    同一通道 → 同一线程 → 操作严格串行；
    不同通道 → 不同线程 → 一路卡死不影响其它路。
    """

    def __init__(self, size: int = 4) -> None:
        self._workers: List[VlcDispatcher] = [
            VlcDispatcher(f"vlc-worker-{i}") for i in range(max(1, int(size)))
        ]

    def __len__(self) -> int:
        return len(self._workers)

    def for_index(self, index: int) -> VlcDispatcher:
        return self._workers[index % len(self._workers)]

    def shutdown(self, timeout_s: float = 12.0) -> bool:
        """等后台把所有 stop/release 跑完，返回是否全部完成。

        窗口在这之前就已经隐藏了，所以用户看到的是瞬间关闭；
        而等 libvlc 干净地停下来再退出，进程才不会留下 0 线程的僵尸条目。
        """
        events = [w.begin_shutdown() for w in self._workers]
        deadline = time.monotonic() + timeout_s
        all_done = True
        for done in events:
            remaining = max(0.0, deadline - time.monotonic())
            if not done.wait(remaining):
                all_done = False
        for worker in self._workers:
            worker.request_quit()
        return all_done


_POOL: Optional[VlcDispatcherPool] = None


def get_pool(size: int = 4) -> VlcDispatcherPool:
    """进程级单例。"""
    global _POOL
    if _POOL is None:
        _POOL = VlcDispatcherPool(size)
    return _POOL
