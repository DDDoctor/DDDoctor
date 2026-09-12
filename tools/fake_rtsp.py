"""黑洞 RTSP 服务器：接受 TCP 连接但永远不发数据。

用来忠实复现「摄像头能连通但不出流」的场景 —— 这正是 libvlc stop() 会长时间
阻塞的典型条件。

    .venv\\Scripts\\python.exe tools\\fake_rtsp.py --port 8554
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

KEEP: list[socket.socket] = []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8554)
    ap.add_argument("--drop-after", type=float, default=0.0, help=">0 则 N 秒后断开")
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.port))
    srv.listen(128)
    print(f"黑洞 RTSP 监听 127.0.0.1:{args.port}（接受连接后不回应）", flush=True)

    def handle(conn: socket.socket) -> None:
        KEEP.append(conn)
        if args.drop_after > 0:
            time.sleep(args.drop_after)
            try:
                conn.close()
            except OSError:
                pass
            return
        # 读一点数据（让对端认为握手开始了），然后彻底沉默
        try:
            conn.settimeout(3600)
            conn.recv(4096)
        except OSError:
            pass
        while True:
            time.sleep(3600)

    while True:
        try:
            conn, addr = srv.accept()
        except OSError:
            break
        print(f"  + 连接来自 {addr}", flush=True)
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
