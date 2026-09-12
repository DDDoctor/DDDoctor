# 多通道视频墙 (MultiView)

**v1.0.5** · Windows 10/11 x64 · 基于 **python-vlc (libvlc) + PySide6**

多路视频流同屏播放器，最多支持 **18 路**通道，可打包成**免安装 VLC** 的可执行程序。

---

## 📦 下载

**最新版：[v1.0.5](https://github.com/DDDoctor/DDDoctor/releases/tag/v1.0.5)**

| 文件 | 说明 |
| --- | --- |
| [MultiView-1.0.5-win64.zip](https://github.com/DDDoctor/DDDoctor/releases/download/v1.0.5/MultiView-1.0.5-win64.zip) | ★ **推荐**：解压后运行 `MultiView\MultiView.exe`，免安装 |
| [MultiView-1.0.5-single.exe](https://github.com/DDDoctor/DDDoctor/releases/download/v1.0.5/MultiView-1.0.5-single.exe) | 单文件版（每次启动需解包约 232 MB，慢 5~15 秒） |
| [MultiView-1.0.5-source.zip](https://github.com/DDDoctor/DDDoctor/releases/download/v1.0.5/MultiView-1.0.5-source.zip) | 源码包（本仓库代码的快照） |
| [SHA256SUMS.txt](https://github.com/DDDoctor/DDDoctor/releases/download/v1.0.5/SHA256SUMS.txt) | 各文件 SHA256 校验值 |

> **发行包（exe / zip）不放在代码目录里**，请到 **[Releases 页面](https://github.com/DDDoctor/DDDoctor/releases)** 下载
> —— 这样仓库只有几百 KB，`git clone` 秒下；要自己构建见 [第 3 节](#3-打包成-exe)。

---

> **文档导航**
> · [使用说明](#1-功能一览)（本文件）
> · [`CHANGELOG.md`](CHANGELOG.md) — 版本历史与缺陷根因
> · [`docs/发布说明-1.0.5.md`](docs/发布说明-1.0.5.md) — 发布产物、部署、已知限制
> · [`docs/架构说明.md`](docs/架构说明.md) — 技术方案与线程模型
> · [`docs/故障排查.md`](docs/故障排查.md) — **遇到问题先看这个**

---

## 1. 功能一览

| 功能 | 说明 |
| --- | --- |
| 多通道任意搭配 | 18 路通道可任意启用/禁用，只有「勾选 + 填了地址」的通道才上屏 |
| 自动网格铺满 | 按通道数和窗口比例自动计算行列，画面尽量铺满窗口且接近 16:9 |
| 弹窗配置 | 一个配置弹窗完成所有设置：通道表格、播放参数、重连策略、目录、界面 |
| 配置持久化 | 配置保存为 `config.json`，支持一键导入 / 导出 |
| 每路独立音量 / 静音 | 每路单独音量（0–200%）与静音，另有一键全局静音 |
| 双击单画面全屏 | 双击某路画面 → 该路铺满整个屏幕（自动隐藏工具栏/菜单栏/状态栏），再次双击或按 `Esc` 还原；`F11` 是普通窗口全屏 |
| 断流自动重连 | 断流、错误、连接超时都会自动重连，按 1x/2x/4x… 指数退避，可设最大次数 |
| 实时状态指示 | 单元格边框颜色 + 标题栏文字显示 连接中 / 缓冲中 / 在线 / 重连中 / 离线 |
| 截图 | 对当前通道截图，PNG 存到截图目录 |
| 录制 | 对当前通道开始/停止录制，文件名为「通道名_时间戳.扩展名」（详见 4.5 的限制说明） |
| 界面不卡死 | 所有阻塞的 libvlc 调用都在后台线程执行；12 路同时起流、断流反复重连时 UI 仍保持响应 |
| 绿色免安装 | 打包后整个文件夹拷走即可运行，内置 VLC 运行库，目标机器无需安装任何东西 |

### 状态颜色

| 颜色 | 含义 |
| --- | --- |
| 灰 `#4a4a4a` | 空闲 / 未播放 |
| 橙 `#e8a33d` | 连接中、缓冲中、重连中 |
| 绿 `#2ecc71` | 在线播放中 |
| 红 `#e74c3c` | 离线、错误（重试耗尽） |
| 蓝 `#2d8cf0` | 当前选中的通道 |

---

## 2. 快速开始（源码运行）

```powershell
# 1) 准备虚拟环境和依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 下载 VLC 运行库到 vendor\vlc（下载 76MB，解压后约 137MB，只需一次）
.\.venv\Scripts\python.exe tools\fetch_vlc.py

# 3) 运行
.\.venv\Scripts\python.exe main.py
```

首次运行会自动生成一份示例配置（1 路 `screen://` 桌面捕获 + 2 路公开测试流），
可以直接点「▶ 播放全部」验证环境是否正常。

---

## 3. 打包成 exe

```powershell
.\build.ps1              # 目录版（推荐：启动快）
.\build.ps1 -OneFile     # 单文件 exe（体积同上，但每次启动要解包，慢 5~15 秒）
```

产物：

```
dist\MultiView\MultiView.exe        # 目录版：把整个 MultiView 文件夹拷给用户
dist\MultiView.exe                  # 单文件版
```

> **为什么推荐目录版**：内置 VLC 运行库 + Qt 共约 250MB，单文件版每次启动都要把
> 这些内容解包到临时目录，视频墙这种需要长时间常驻的程序用目录版体验好得多。

打包内容：

* 内置 `vendor\vlc\`（`libvlc.dll` / `libvlccore.dll` / `vlc.exe` / `plugins\`，约 137MB）
* Qt 只打包用到的 `QtCore / QtGui / QtWidgets` 及必要插件，其余模块在 `MultiView.spec` 中被排除

实测打包体积：**目录版约 232 MB**（其中 VLC 137 MB、PySide6 72 MB）。

> ⚠️ 修改 `MultiView.spec` 的 `EXCLUDES` 时要小心：排除掉 PySide6 真正依赖的模块
> （例如 `shiboken6.Shiboken`）会导致 exe 启动时报
> `Failed to execute script 'main' ... No module named 'xxx'`。

---

## 4. 使用说明

### 4.1 配置通道

点工具栏 **配置…**（`Ctrl+,`）→ **通道配置** 页：

| 列 | 说明 |
| --- | --- |
| 启用 | 勾选后该通道参与画面网格；未勾选或没填地址都不会上屏 |
| 通道名称 | 显示在画面标题栏，也是截图/录制文件的文件名前缀 |
| 流地址 | 支持 `rtsp://` `rtmp://` `http(s)://`（HLS/FLV/MP4）`udp://` `rtp://` `screen://`（桌面捕获）以及本地文件路径 |
| 音量 | 该通道音量，0–200%（超过 100% 为软件放大，可能失真） |
| 静音 | 该通道是否静音 |

**批量导入地址**：点「批量导入地址…」，每行一个通道，支持三种写法：

```
大门,rtsp://192.168.1.64:554/Streaming/Channels/101
车间 rtsp://192.168.1.65:554/Streaming/Channels/101
http://192.168.1.66:8080/live.flv
# 以 # 开头的行会被忽略
```

### 4.2 播放设置

| 项 | 建议 |
| --- | --- |
| 网络缓存 | 局域网 200–500ms；公网/弱网 1000–3000ms。越大越抗抖动、延迟越高 |
| RTSP 传输 | 建议保持「走 TCP」，穿透 NAT、抗丢包更好 |
| 硬件解码 | 多路 1080P 时开启（默认自动）可大幅降低 CPU；若出现花屏/绿屏改成「关闭」 |
| 视频填充方式 | 「保持比例」= 黑边不变形；「拉伸铺满」= 强制填满单元格（会变形） |

### 4.3 断流重连

断流 / 解码错误 / 超过「连接超时」未出画面，都会触发重连：首次等待 N 秒，
之后 2N、4N、8N…（最长 60 秒一次）。「最大重试次数」设 0 表示无限重试。

### 4.4 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Space` | 播放全部 / 停止全部（交替） |
| `F11` | 窗口全屏切换（单画面全屏时按它 = 还原） |
| `Esc` | 退出单画面全屏 / 还原放大 / 退出全屏 |
| `Ctrl+F` | 单画面全屏或还原「当前通道」 |
| `Ctrl+S` | 对当前通道截图 |
| `Ctrl+R` | 对当前通道开始 / 停止录制 |
| `Ctrl+,` | 打开配置弹窗 |
| `Ctrl+Q` | 退出 |
| 单击画面 | 选中该通道（工具栏「当前通道」下拉框同样可以选） |
| 双击画面 | **单画面全屏 / 还原** |

> 双击行为可在「配置 → 界面 → 双击行为」里改：取消勾选后，双击只在窗口内把该路
> 放大铺满网格区，保留工具栏。

> 提示：某些显卡驱动下 VLC 的视频窗口会吞掉鼠标消息，此时请用
> 工具栏的「当前通道」下拉框选择通道，或双击**标题栏**——功能完全一致。

### 4.5 声音

**只有没勾「静音」的通道才会出声。** 多路同时出声会互相盖住，所以默认只有第一路出声。

* 每格画面标题栏有个小喇叭：**🔊 绿色 = 在出声**，**🔇 灰色 = 静音**
* 工具栏 **🎧 仅此路出声**：只让「当前通道」出声，其余全部静音（监控墙最常用）
* 工具栏 **🔇 当前通道静音** / 快捷键 `Ctrl+M`：单独切换某一路
* 工具栏 **全局静音**：一键全部静音 / 恢复

> **排查"没有声音"**：先用上面的喇叭图标确认该路不是 🔇；再确认系统音量、
> 默认播放设备；最后确认**流本身有没有音轨** —— 很多摄像头主码流是纯视频，
> 设备端要先打开麦克风/音频编码。
> 可以用 `tools/audio_probe.py --url <流地址>` 直接查该流有几条音轨。

### 4.6 截图与录制

* **截图**：`Ctrl+S`，PNG 存到「截图目录」，文件名 `通道名_时间戳.png`。
* **录制**：`Ctrl+R` 开始/停止（画面上会出现红点 `● REC`），文件名 `通道名_时间戳.扩展名`，
  保存在「录制目录」。
* 「文件 → 打开截图目录 / 打开录制目录」可以直接跳到对应文件夹。

> **关于录制的两点说明（重要）**
>
> libvlc 3.x 的 C API **没有**提供录制开关函数，因此录制是通过 VLC 的 sout 管线实现的：
>
> ```
> #duplicate{dst=display,dst=std{access=file,mux=ts,dst=<文件路径>}}
> ```
>
> 由此带来两个必然的限制：
>
> 1. **开始/停止录制会让该通道重新连接一次**（约 1 秒黑屏），其它通道不受影响；
> 2. **正在录制的通道无法截图**——sout 模式下 VLC 不注册可截图的 vout。
>    需要截图时先停止录制即可（程序会给出对应提示）。
>
> 封装格式建议：直播流用 **TS**（默认，最稳）；MKV 容错性也很好；
> **MP4 不适合直播流**（程序异常退出时文件会损坏）。

---

## 5. 目录结构

```
.
├─ main.py                  程序入口
├─ app/                     源代码
│  ├─ main_window.py        主窗口：工具栏、菜单、状态栏、各种操作
│  ├─ wall.py               自动网格布局计算与摆放
│  ├─ cell.py               单个通道画面单元（标题栏 + 画面 + 状态层）
│  ├─ player.py             libvlc 封装：播放、事件、自动重连、截图、录制
│  ├─ dispatch.py           后台线程池：把阻塞的 libvlc 调用挪出 UI 线程
│  ├─ vlc_runtime.py        定位/接入内置或系统 VLC 运行库
│  ├─ settings_dialog.py    配置弹窗（含批量导入）
│  ├─ config.py             配置数据模型 + JSON 读写 + 目录迁移
│  ├─ constants.py          常量（状态、颜色、上限）
│  ├─ sysinfo.py            进程内存查询
│  └─ paths.py              路径解析（源码 / 打包后）
├─ tools/                   开发与运维工具（详见 tools/README 小节）
├─ assets/multiview.ico     程序图标
├─ vendor/vlc/              内置 VLC 运行库（打包时一起带走，约 137MB）
├─ samples/                 配置样例
│  ├─ config.demo.json      6 路公开测试流演示配置
│  └─ config.11ch-轨道车辆.json  11 路车载 NVR 配置样例
├─ docs/                    文档
│  ├─ 发布说明-1.0.5.md
│  ├─ 架构说明.md
│  ├─ 故障排查.md
│  └─ 卡死现场记录-py-spy.txt   一次真实卡死的线程堆栈现场
├─ release/                 发布产物（exe / zip / 源码包 / SHA256）
├─ CHANGELOG.md             版本历史与缺陷根因记录
├─ README.md                本文件
├─ MultiView.spec           PyInstaller 打包配置
├─ build.ps1                一键构建脚本
└─ requirements.txt
```

### 5.1 tools/ 工具一览

| 工具 | 用途 |
| --- | --- |
| `fetch_vlc.py` | 下载并抽取 VLC 运行库到 `vendor/vlc` |
| `make_icon.py` | 生成 `assets/multiview.ico` |
| `verify_build.py` | **校验打包产物是否完整**（防止文件被占用导致半成品） |
| `portable_check.py` | 解压到临时目录跑一遍，验证「换目录也能用」 |
| `smoke_test.py` | 播放 + 截图 + 录制 全链路自检 |
| `demo_config.py` | 生成 N 路公开测试流的演示配置 |
| `stress_config.py` | 生成 N 路「连不上」的压力测试配置 |
| `inspect_config.py` | 查看配置里的通道 / 音量 / 静音 / 目录 |
| `migrate_check.py` | 验证旧配置的目录迁移是否正确 |
| `url_probe.py` | **逐个试探 RTSP 地址是否可用**（找设备通道号写法） |
| `cells_probe.py` | **逐路检查画面**：状态 / 有无 vout / 绑定的窗口句柄是否有效 |
| `audio_probe.py` | 查某条流有几条音轨、音量与静音状态 |
| `audio_verbose.py` | 用 VLC verbose 日志确认音频输出是否真的建立 |
| `monitor.py` | **长时间监控**：卡死瞬间自动抓线程堆栈 + 截图 + 日志 |
| `hang_probe.py` | 检测窗口是否被阻塞（WM_NULL + SMTO_ABORTIFHUNG） |
| `block_probe.py` | 测量各阻塞调用的实测耗时 |
| `settings_repro.py` | 复现/验证「配置 → 确定」路径是否阻塞 |
| `dblclick_test.py` | 验证双击事件的触发次数与全屏行为 |
| `capture.py` / `click.py` / `close_app.py` | 抓屏 / 模拟点击 / 模拟关闭窗口 |
| `hw_probe.py` | 对比硬解与软解的 CPU 占用 |
| `fake_rtsp.py` | 黑洞 RTSP 服务（接受连接但不发数据），用于复现设备卡住 |

### 5.2 自检

```powershell
# 播放 + 截图 + 录制 全链路自检（约 30 秒）
.\.venv\Scripts\python.exe tools\smoke_test.py

# 打包完整性校验
.\.venv\Scripts\python.exe tools\verify_build.py dist\MultiView
```

打包后运行时的目录：

```
MultiView\
├─ MultiView.exe
└─ _internal\
   ├─ vlc\                  内置 VLC 运行库
   └─ ...                   Qt / Python 运行时
```

程序运行时会优先把 `config.json`、`multiview.log`、`snapshots\`、`recordings\`
放在 **exe 所在目录**；如果该目录不可写（例如装在 `C:\Program Files`），
会自动退回到 `%APPDATA%\MultiView`。

**截图/录制目录默认是「相对程序目录」的**，配置里存的是 `snapshots` / `recordings`
这样的相对路径，所以**换版本、挪动文件夹时会自动跟着走**，不会写回旧版本目录。

> v1.0.5 之前版本把默认目录存成了绝对路径，导致换了新版目录后录制仍然写进旧目录
> （旧目录被删掉还会被重新创建）。v1.0.5 载入旧配置时会自动把它改回相对路径；
> 手动指定过别的位置（如 `E:\录像`）的配置不受影响。

---

## 6. 常见问题

**Q：不管配多少路，总有一路（或几路）黑屏 / 一直"重连中"？**
**先检查这几路的流地址是不是同一个。** 用同一台设备反复拉同一路码流会触发设备的
并发连接数上限，超出的连接被拒绝 → 黑屏。日志里会看到 `通道 N 连接失败`。

实测案例：11 路全部填 `rtsp://192.168.1.10:554/Streaming/Channels/1` →
**8 路在线、3 路连接失败**。改成各自的通道地址即可。

不确定设备的通道号怎么写？直接探：

```powershell
.\.venv\Scripts\python.exe tools\url_probe.py --host 192.168.1.10
```

也可以用 `tools/cells_probe.py` 逐路检查程序侧状态（有无视频输出、句柄是否有效），
区分是"程序问题"还是"设备/地址问题"。详见 [`docs/故障排查.md`](docs/故障排查.md)。

**Q：提示「缺少 VLC 运行库」？**
确认程序目录下存在 `vlc\libvlc.dll` 和 `vlc\libvlccore.dll`；
也可安装 64 位 VLC，或用环境变量 `MULTIVIEW_VLC_DIR` 指定 VLC 目录。

**Q：某些通道一直「重连中」？**
1. 用 VLC 播放器直接打开这个地址，确认地址和账号密码正确；
2. RTSP 建议勾选「走 TCP」；
3. 海康/大华等设备有**并发连接数上限**，18 路同开可能需要调高设备的连接数；
4. 增大「网络缓存」和「连接超时」。

**Q：画面花屏、绿屏、马赛克？**
把「硬件解码」改为「关闭（软件解码）」再试，这是显卡驱动兼容性问题。

**Q：18 路卡顿？**
* 确认开启了硬件解码；
* 网络带宽：单路 1080P H.264 约 2–8Mbps，18 路需要 **40–150Mbps** 的稳定内网带宽，
  以及对应的交换机背板带宽；
* 降分辨率/码率，或使用设备的子码流（Sub Stream）地址。

**Q：想调整某路画面的比例？**
「播放设置 → 视频填充方式」是全局的；「保持比例」适合绝大多数监控流。

**Q：录制中截图失败？**
这是 libvlc 3.x 的固有限制（sout 录制模式下没有可截图的 vout），先停止录制再截图即可。

**Q：开始/停止录制时画面卡了一下？**
同样是 sout 机制导致的必然重连，约 1 秒，其它通道不受影响。

**Q：开多路之后界面卡死 / 点不动？（v1.0.3 已彻底修复）**

真正的根因是 **libvlc 的 input 锁争用**，不是 CPU 或内存：

`libvlc_media_player_stop()` 会长时间持有 libvlc 的 input 锁（车载 NVR 断流时
单次可达 3 秒）。而下面这些看似"无害"的接口内部都要先 `libvlc_get_input_thread()`
去抢同一把锁：

```
libvlc_video_set_aspect_ratio()   libvlc_video_set_scale()
libvlc_audio_set_volume()         libvlc_audio_set_mute()
libvlc_video_take_snapshot()
```

只要它们还在 UI 线程上执行，而同时后台正有 stop() 在跑，**主线程就会排队等锁**。
最典型的触发路径就是「配置 → 确定」：

```
open_settings  →  stop_all()（11 路 stop 丢给 4 个后台线程，把锁占住）
               →  _rebuild_wall() → apply_config() → video_set_aspect_ratio()
               →  主线程等锁 → 界面卡死十几秒
```

现场抓到的堆栈（py-spy）：

```
Thread "MainThread"                ← UI 主线程
    libvlc_video_set_aspect_ratio (vlc.py:11468)
    video_set_aspect_ratio (vlc.py:3437)
    _apply_fit (app\player.py:487)
    apply_config (app\player.py:469)
    _apply_channel_audio (app\main_window.py:293)
    _rebuild_wall (app\main_window.py:252)
    open_settings (app\main_window.py:528)
Thread ×4                          ← 4 个后台线程全部堵在这里
    libvlc_media_player_stop (vlc.py:10049)
    _stop_job (app\player.py:458)
```

v1.0.3 起这些调用也全部走后台线程，`_rebuild_wall()` 在 11 路全断流的场景下
从 **十几秒降到 162 ms**。

**Q：双击关闭/退出时也要等一下？**
关窗口会**先隐藏窗口**，用户看到的是瞬间关闭；然后程序在后台等每一路的
`stop()` / `release()` 干净地跑完（实测 0.02 秒，最长给 12 秒）才真正退出。
这样进程能干净收尾 —— 不等它、或用 `QThread.terminate()` 强杀后台线程，
都会留下**杀不掉的 0 线程僵尸进程**（实测关闭要 9~14 秒）。

**Q：多路 1080P 的机器配置要求？**
本机实测（8 核 CPU + 集显，H.264 1080P 约 3Mbps）：

| 项目 | 实测值 |
| --- | --- |
| 单路 CPU（硬解，默认） | 约 0.14 个核心 |
| 单路 CPU（软解） | 约 0.21 个核心 |
| 单路内存 | 约 200–250 MB |
| 18 路估算 | 约 2.5–4 个核心 + 4 GB 内存 |

结论：**18 路建议 8 核 CPU / 16GB 内存**；内存比 CPU 更容易先成为瓶颈。
「配置 → 播放设置 → 硬件解码」保持「自动」即可，实测硬解比软解省约 1/3 CPU；
若出现花屏再改成「关闭」。

**Q：视频画面为什么点不动 / 双击没反应？**
VLC 的视频输出窗口在某些显卡驱动下会吞掉鼠标消息。v1.0.2 起即使遇到这种情况，
标题栏（通道名那一条）双击同样可以单画面全屏，工具栏的「放大/还原」按钮也可以。

> v1.0.1 及更早版本有个 bug：双击会**闪一下但不生效**。原因是 Qt 的鼠标事件默认
> 不被接受时会向父控件冒泡，双击被 `_VideoSurface` 和 `VideoCell` 各处理了一次，
> 于是「全屏」后立刻又「还原」。v1.0.2 已修复（事件显式 `accept()`）。

**Q：`config.json` 在哪里？**
见第 5 节，一般是 exe 同目录；也可以在「帮助 → 关于」里看到完整路径。

---

## 7. 技术说明

* **为什么用 libvlc 而不是 QtMultimedia**：libvlc 对 RTSP/RTMP/HLS/组播的支持最完善，
  硬解、丢包恢复、协议兼容性都远好于 Qt 自带后端。
* **一个 libvlc 实例 + N 个 MediaPlayer**：18 路共享一个 `libvlc_instance_t`，
  每个通道一个 `libvlc_media_player_t`，资源占用比开 18 个 VLC 进程低得多。
* **渲染方式**：`media_player.set_hwnd()` 把 VLC 的视频输出嵌到 Qt 部件的窗口句柄上，
  这是 Windows 下最稳、性能最好的内嵌方式。
* **线程模型**：libvlc 的事件回调运行在 VLC 自己的线程里，所有回调只做一件事——
  `emit` 一个 Qt 信号，真正的界面更新和状态机全部在主线程执行。
* **阻塞调用隔离**：libvlc 3.x 的 `stop()` / `set_media()` / `play()` / `release()`
  都是同步阻塞的，而且**没有** `stop_async`（那是 VLC 4.0 的 API）。
  更麻烦的是 `video_set_aspect_ratio()` / `video_set_scale()` / `audio_set_*()` /
  `video_take_snapshot()` 内部都要抢 libvlc 的 **input 锁**——只要后台有 stop() 在跑，
  这些调用就会在 UI 线程上排队等锁。
  **所有**这些接口统一提交给 `app/dispatch.py` 的后台工作线程池：
  同一通道固定分派到同一线程（保证操作串行），4 个线程轮转（保证一路卡死不影响其它路）。
* **后台线程实现**：不用 `QThread`，而是普通 Python **守护线程 + `queue.Queue`**。
  QThread 对象在解释器退出时被析构、而线程还在跑，Qt 会 `qFatal`，
  导致进程 9 秒退不掉并留下僵尸。守护线程没有 Qt 对象生命周期问题。
* **启动错峰**：超过 6 路时，每 250ms 起一路，避免十几路同时初始化解码器造成 CPU 尖峰。
* **界面节流**：VLC 的 buffering 事件非常密集，缓冲百分比刷新被节流到 2 次/秒；
  单元格样式表做了缓存，避免高频 `setStyleSheet` 触发整棵子控件树的样式重算。

---

## 8. 许可

* 本项目代码：可自由使用/修改。
* 内置的 VLC 运行库遵循 **GPLv2+**（VideoLAN 项目），分发时请一并遵守其许可条款。
