"""下载 VLC for Windows (x64) 并抽取运行所需的文件到 vendor/vlc。

只保留播放流媒体真正需要的部分：
    libvlc.dll / libvlccore.dll / plugins/

用法：
    python tools/fetch_vlc.py            # 自动下载最新 3.0.x
    python tools/fetch_vlc.py --zip X.zip
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "vendor" / "vlc"

VERSION = "3.0.23"
URLS = [
    f"https://download.videolan.org/videolan/vlc/{VERSION}/win64/vlc-{VERSION}-win64.zip",
    f"https://mirrors.tuna.tsinghua.edu.cn/videolan-ftp/vlc/{VERSION}/win64/vlc-{VERSION}-win64.zip",
    f"https://mirror.freedif.org/videolan/vlc/{VERSION}/win64/vlc-{VERSION}-win64.zip",
]

KEEP_FILES = {"libvlc.dll", "libvlccore.dll", "vlc.exe"}
KEEP_DIRS = {"plugins"}


def _download(dest: Path) -> Path:
    last_error: Exception | None = None
    for url in URLS:
        try:
            print(f"下载 {url}")
            with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh, 1024 * 256)
            size = dest.stat().st_size
            if size < 5_000_000:
                raise RuntimeError(f"下载内容过小（{size} 字节），可能不是压缩包")
            print(f"完成：{size / 1024 / 1024:.1f} MB")
            return dest
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"  失败：{exc}")
    raise SystemExit(f"所有镜像均下载失败：{last_error}")


def extract(zip_path: Path) -> None:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        root = names[0].split("/")[0] + "/"
        count = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = info.filename[len(root):] if info.filename.startswith(root) else info.filename
            if not rel:
                continue
            top = rel.split("/")[0]
            if rel in KEEP_FILES:
                target = TARGET / rel
            elif top in KEEP_DIRS:
                target = TARGET / rel
            else:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1

    required = ["libvlc.dll", "libvlccore.dll"]
    missing = [f for f in required if not (TARGET / f).is_file()]
    if missing:
        raise SystemExit(f"解压后缺少文件：{missing}")

    total = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file())
    print(f"已抽取 {count} 个文件到 {TARGET}（{total / 1024 / 1024:.1f} MB）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", help="使用本地已有的 VLC zip 包")
    ap.add_argument("--keep-zip", action="store_true", help="保留下载的 zip")
    args = ap.parse_args()

    if args.zip:
        extract(Path(args.zip))
        return 0

    tmp = ROOT / "build_cache" / f"vlc-{VERSION}-win64.zip"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if not tmp.is_file() or tmp.stat().st_size < 5_000_000:
        if tmp.exists():
            tmp.unlink()
        _download(tmp)
    else:
        print(f"复用已下载的压缩包：{tmp}")
    extract(tmp)
    if not args.keep_zip:
        tmp.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
