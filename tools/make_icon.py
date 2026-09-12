"""生成 assets/multiview.ico（四宫格图标）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen

    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    for size in sizes:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        radius = size * 0.18
        p.setBrush(QBrush(QColor("#12151a")))
        p.setPen(QPen(QColor("#2d8cf0"), max(1.0, size * 0.045)))
        p.drawRoundedRect(
            QRectF(size * 0.03, size * 0.03, size * 0.94, size * 0.94), radius, radius
        )

        pad = size * 0.16
        gap = size * 0.055
        cell = (size - 2 * pad - gap) / 2
        colors = ["#2ecc71", "#2d8cf0", "#e8a33d", "#e74c3c"]
        p.setPen(Qt.PenStyle.NoPen)
        for i, color in enumerate(colors):
            r, c = divmod(i, 2)
            x = pad + c * (cell + gap)
            y = pad + r * (cell + gap)
            p.setBrush(QBrush(QColor(color)))
            p.drawRoundedRect(QRectF(x, y, cell, cell), size * 0.03, size * 0.03)
        p.end()
        images.append(img)

    out = ROOT / "assets"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "multiview.ico"

    # Qt 的 ICO 写入只保存单张图，这里手工拼装多尺寸 ICO
    import struct

    pngs = []
    for img in images:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        pngs.append(bytes(buf.data()))
        buf.close()

    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for img, data in zip(images, pngs):
        w = 0 if img.width() >= 256 else img.width()
        h = 0 if img.height() >= 256 else img.height()
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    target.write_bytes(header + entries + blobs)
    print(f"已生成 {target} ({target.stat().st_size} 字节, {len(pngs)} 种尺寸)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
