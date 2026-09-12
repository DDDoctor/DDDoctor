# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

    pyinstaller --noconfirm --clean MultiView.spec                     # 目录版（推荐）
    $env:MV_ONEFILE='1'; pyinstaller --noconfirm --clean MultiView.spec  # 单文件版

内置 VLC 运行库位于 vendor/vlc，打包后解包到 exe 同级（目录版）或临时目录（单文件版）
的 vlc/ 子目录，由 app.vlc_runtime 自动定位。
"""

import os
from pathlib import Path

ONEFILE = os.environ.get("MV_ONEFILE", "") == "1"
ROOT = Path(SPECPATH)
ICON = ROOT / "assets" / "multiview.ico"

EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "lib2to3",
    "test",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtHelp",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtNetworkAuth",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtWebView",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "vendor" / "vlc"), "vlc")],
    hiddenimports=["vlc"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

_common = dict(
    name="MultiView",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON) if ICON.is_file() else None,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **_common)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_common)
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="MultiView",
    )
