"""全局常量。"""

from __future__ import annotations

APP_NAME = "MultiView"
APP_TITLE = "多通道视频墙"
APP_VERSION = "1.0.5"

#: 最大支持的通道数量
MAX_CHANNELS = 18

#: 通道标题栏高度（像素）
HEADER_HEIGHT = 24

# ---------------------------------------------------------------- 运行状态 ----

STATE_IDLE = "idle"                # 未启用 / 未播放
STATE_CONNECTING = "connecting"    # 正在连接
STATE_BUFFERING = "buffering"      # 缓冲中
STATE_PLAYING = "playing"          # 播放中
STATE_RECONNECTING = "reconnecting"  # 断流重连中
STATE_OFFLINE = "offline"          # 已停止 / 重试耗尽
STATE_ERROR = "error"              # 出错

STATE_TEXT = {
    STATE_IDLE: "空闲",
    STATE_CONNECTING: "连接中",
    STATE_BUFFERING: "缓冲中",
    STATE_PLAYING: "在线",
    STATE_RECONNECTING: "重连中",
    STATE_OFFLINE: "离线",
    STATE_ERROR: "错误",
}

#: 边框 / 状态点颜色
STATE_COLOR = {
    STATE_IDLE: "#4a4a4a",
    STATE_CONNECTING: "#e8a33d",
    STATE_BUFFERING: "#e8a33d",
    STATE_PLAYING: "#2ecc71",
    STATE_RECONNECTING: "#e8a33d",
    STATE_OFFLINE: "#e74c3c",
    STATE_ERROR: "#e74c3c",
}

# ------------------------------------------------------------ 视频填充方式 ----

FIT_KEEP = "keep"        # 保持原始宽高比，黑边填充
FIT_STRETCH = "stretch"  # 拉伸铺满窗口

FIT_TEXT = {
    FIT_KEEP: "保持比例（黑边）",
    FIT_STRETCH: "拉伸铺满",
}

# ------------------------------------------------------------ 硬件解码方式 ----

HW_DECODE_TEXT = {
    "any": "自动（推荐）",
    "d3d11va": "D3D11VA",
    "dxva2": "DXVA2",
    "none": "关闭（软件解码）",
}

# ------------------------------------------------------------ 录制封装格式 ----

RECORD_MUX_TEXT = {
    "ts": "TS (MPEG-TS)",
    "mkv": "MKV (Matroska)",
    "mp4": "MP4",
}
