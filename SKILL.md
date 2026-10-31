---
name: use-computer-pro
displayName: Use computer pro
description: 桌面自动化总控技能。像人一样操作本机 Windows 桌面与 VMware 虚拟机（VNC 键鼠注入、vmrun 客户机执行、客户机内截图），统一调度 windows-mcp、windows-control 脚本、Rebind 三条通道，并给出坐标换算、动作校验、故障排查的完整方法。当任务需要看屏幕、点按钮、填表单、敲命令、操作无 API 的 GUI 软件，或在虚拟机里做实验、抓过程截图时使用。Use when the task needs to operate a GUI, e.g. click, type, screenshot, drive a VM, or automate desktop workflows.
description_zh: 桌面自动化总控：本机 Windows 与 VMware 虚拟机的统一操作方法，含三条控制通道的选型、坐标换算、校验闭环与故障速查。
description_en: Unified desktop automation for local Windows and VMware guests, with channel selection, coordinate math, verify-loops and a troubleshooting playbook.
version: 1.0.0
agent_created: true
tags:
  - computer-use
  - desktop-automation
  - vmware
  - vnc
  - windows
  - screenshot
---

# Use computer pro

一套"看得见、点得准、能自证"的桌面操作方法论。核心不是某个工具，而是**通道选型 + 坐标换算 + 动作校验 + 故障归因**这条闭环。

本技能融合三个来源：`windows-mcp` 工具集、`windows-control` 脚本集（pyautogui / pywinauto）、`rebind-pc-auto-control`（Rebind MCP），再加上 VMware 虚拟机远程控制（VNC / vmrun）的实战经验。

---

## 0. 开工前三十秒

1. 目标在哪：本机桌面 / 本机上的虚拟机 / 远程主机。**决定用哪条通道，比急着点更重要。**
2. 有没有比 GUI 更硬的接口：命令行、配置文件、COM、注册表、数据库、API。能用接口就别点鼠标。
3. 需不需要留证：要截图存档的任务，从一开始就按"每步一张图"的节奏做，别事后补。
4. 有没有会锁死输入的东西：全屏程序、RDP 窗口、虚拟机控制台、UAC 安全桌面、模态对话框。

---

## 1. 通道选型

| 场景 | 首选 | 备选 | 备注 |
|---|---|---|---|
| 本机 Windows 应用 | `mcp__windows-mcp__Snapshot` + `Click`/`Type` | `windows-control` 脚本 | MCP 能拿到元素 label/id，比坐标稳 |
| 本机批量/脚本化 | `windows-control/scripts/*.py` | MCP | 一次命令做一串动作时更省调用 |
| 本机 + 需要复杂编排 | Rebind（`ws://127.0.0.1:19561`） | 上面两者 | 需先装 Rebind 与 bun |
| VMware 里的客户机 | 客户机 VNC（键鼠 + 画面） | 控制台 + SendInput | 控制台注入极不稳定，见 §4 |
| 客户机里跑命令/取文件 | `vmrun` guest ops | 客户机内起 HTTP 服务 | 需要 VMware Tools |
| 客户机截图留证 | 客户机内截图（`import`/PowerShell） | `vmrun captureScreen` | 后者要 Tools，客户机挂了会挂起 |
| Linux 桌面 | `xdotool` + `import`/`xwd` | VNC | 见 §5 |

**判定口诀**：能用 UI 树就不用坐标；能用客户机内执行就不用模拟键盘；能用 VNC 就不用控制台。

---

## 2. 闭环：感知 → 动作 → 校验

```
Snapshot/截图  →  定位元素  →  单个动作  →  再截图/读树确认  →  下一步
                     ↑                              |
                     └──────── 不符合预期则重判 ←────┘
```

硬性要求：

- **一个动作一次校验**。连续盲点三次以上，几乎一定是通道或坐标错了，停下来重判，别加重试次数。
- **动作原子化**。不要在一条命令里点三下、敲五行，出错时无法定位是哪一步。
- **先聚焦再操作**。点击前确认目标窗口在前台（`App(mode="switch")` 或 `focus_window.py`），否则点击落在遮挡窗口上。
- **等待用条件，不用固定 sleep**。`mcp__windows-mcp__WaitFor(condition="text_exists"|"active_window"|"element_exists")`；虚拟机里没有 WaitFor 时才用短 sleep 轮询截图。

---

## 3. 坐标：绝大多数"点不中"都出在这里

**四个换算层，缺一不可：**

1. **截图缩放**：MCP 返回的图可能被压缩。文档明确写了——按 `原图尺寸 / 显示尺寸` 的比例把图上坐标放大回屏幕坐标。
2. **DPI 缩放**：进程必须先 `SetProcessDPIAware()`，否则 125%/150% 缩放下坐标整体偏移。pyautogui 在部分环境同样受影响。
3. **多屏偏移**：屏幕原点可能为负（副屏在左侧）。`ImageGrab.grab(bbox=..., all_screens=True)` 才抓得到负坐标区域。
4. **窗口相对 vs 屏幕绝对**：`GetWindowRect` / pygetwindow 的 `left/top` 是屏幕坐标；客户机里的截图坐标是**客户机自己的**屏幕坐标，两者不能混用。

**取坐标的稳法：**

- UI 树优先：`windows-control/scripts/read_ui_elements.py "窗口名" --json`，直接拿元素的 rect。
- 名称优先：`click_element.py "保存"`、`click_text.py "登录"`，绕开坐标。
- 实在要目测：在截图上叠坐标网格（画 50/100px 刻度并标注数值），**读标注的数值，不要读屏幕上的像素位置**。这一条踩过坑：图被缩放后按"看到的像素"取数，全部偏了 1.18 倍。
- 拿不准就用"宽框"打标：先画一个明显过大的框，再二分收缩，比一次到位快。

---

## 4. 输入原语与陷阱

### 4.1 鼠标

- **单击只能有一次按下/释放**。为了"保险"连发两次按下，会被系统识别成双击：列表项被打开、图标被启动、单选按钮反复切换。踩过的坑：本想选中服务列表某一行，结果弹出了服务属性对话框。
- **双击要在同一连接/同一序列内完成**（两次间隔 < 500ms）。跨进程调两次 click 往往变成两次单击。
- **点单选按钮/复选框，点标签文字**。那个直径 12px 的圆圈，偏 2px 就点空，且界面毫无反馈。
- **拖拽必须有中间移动帧**：按下 → 移动若干中间点 → 抬起。一步跳到终点，很多控件识别不到拖拽。
- 右键用 `button="right"`，上下文菜单弹出后再逐项点击，不要连发。

### 4.2 键盘

- 修饰键必须成对：按下 Ctrl → 按键 → 释放 Ctrl。**中途抛异常会留下卡住的 Ctrl/Alt**，表现为后续所有按键都变成快捷键。写脚本时把解析键名的步骤放在发送之前，异常就不会发生在"已按下未释放"之间。
- VNC / 远程注入常用 keysym：Enter `0xFF0D`、Esc `0xFF1B`、Tab `0xFF09`、Win `0xFFEB`、F1–F12 `0xFFBE + n-1`。
- **中文不要逐字打**：远程键盘只认 keysym，打中文要么失败要么乱码。用剪贴板：`Clipboard(mode="set")` → `Shortcut("ctrl+v")`。
- Windows 控制台（cmd）里的方向键、End、PageUp 依赖焦点：先点一下窗口内部再发键。

### 4.3 文本与编码

- 中文 Windows 控制台默认代码页 936。把输出经管道/网络送到 UTF-8 终端必然乱码，`chcp 65001` 之后再执行命令即可。
- 写文件一律 UTF-8；但 `.vmx`、部分系统配置文件要用 ANSI/UTF-8 无 BOM，用 PowerShell `Set-Content -Encoding Default` 更稳。
- 传输中文路径给命令行程序时，优先用 PowerShell 工具而不是 bash，避免 GBK/UTF-8 转码失败。

### 4.4 焦点：重连之后的第一件事

远程通道（VNC / RDP / MCP）重连只恢复了**管道**，没有恢复**焦点**。上一次会话结束时窗口处于什么状态，新连接就继承什么状态——很可能根本没有焦点。

真实翻车：重连后直接 `text("msfconsole")`，按键全部落进桌面的应用搜索框，屏幕上多出一个启动器、命令被拆成碎片。更糟的是这个搜索框还抢走了后续所有按键。

固定动作，不要省：

```
connect → grab(full=True)        # 先确认画面
        → click(窗体内部一个安全点)  # 拿到焦点
        → 再发任何按键
```

"安全点"选空白区、标题栏、或已知无副作用的区域；不要点按钮。键盘发送前若无法确认焦点，宁可多一次 click + 一次截图校验。

---

## 5. VMware 虚拟机专项（本技能的重点）

### 5.1 打开客户机的 VNC 通道

关机状态下在 `.vmx` 追加三行，再开机：

```
RemoteDisplay.vnc.enabled = "TRUE"
RemoteDisplay.vnc.port = "5910"
RemoteDisplay.vnc.password = "vkali"
```

要点：

- **必须关机改**，运行中改无效。
- **一定设密码**。留空时部分版本握手后直接断开（TCP 建连成功但读 12 字节 banner 就 EOF）。
- 每个 VM 用不同端口（5910/5911/…），避免冲突。
- 只监听 127.0.0.1，不要 `vnc.allowRemote`，更不要映射到公网。

### 5.2 VNC 协议实现要点（自己写客户端时）

- 握手：服务端先发 `RFB 003.008\n`；客户端回版本后读安全类型数量与列表；选 `2`（VNC 认证）→ 读 16 字节挑战 → 用密码作 DES 密钥加密回发 → 读 4 字节结果（0 成功）。
- 密码处理：取前 8 字节补 0，**每字节比特反序**后作为 DES 密钥（见 `scripts/des.py`，内含标准测试向量）。
- `SetPixelFormat` 可以省，默认就是 32bpp、shift 16/8/0、小端。
- `SetEncodings` 的 **count 必须等于后面真正写的编码个数**。写 count=0 却追加了两个编码，服务器会静默挂起，表现为请求帧缓冲一直超时。
- 帧缓冲请求 `incremental=0` 拿全帧；但**长连接下服务器只发变化区域**，客户端必须自己缓存上一帧再叠加，否则画面出现大片黑块。
- 客户机改分辨率后，不申请 `DesktopSize(-223)` 伪编码的话，客户端画面尺寸不会跟着变——重连一次最省事。

### 5.3 控制台被"抢鼠标"的识别与解法

症状：`SetCursorPos` 返回 0，`GetCursorPos` 纹丝不动；`mouse_event` 绝对/相对都不动；程序化键盘也没反应。

按顺序排查：

1. **有没有模态对话框**。VMware 的"可移动设备""客户机操作系统已禁用 CPU"这类框会独占输入。枚举该进程的顶层窗口，标题里带这些字样就先关掉（`WM_CLOSE`，关不掉就 `pywinauto` 找按钮点）。
2. **控制台是否 grab 了指针**。虚拟机窗口处于"已捕获输入"状态时，主机光标被锁在窗口内。
3. **重启 UI 释放**：`Stop-Process -Name vmware`（只杀界面进程）。虚拟机本体在 `vmware-vmx.exe` 里继续运行，重新 `Start-Process vmware.exe` 后库列表里点开即可恢复，**不会丢虚拟机状态**。
4. 反例：切前台窗口、`ClipCursor(NULL)`、反复 `ShowCursor` 基本无效，别在这上面耗时间。

### 5.4 vmrun 常用命令与坑

```powershell
$vmrun = "D:\app\VMware\VMware Workstation\vmrun.exe"
& $vmrun -T ws list                                    # 正在运行的 VM
& $vmrun -T ws start  <vmx> gui                        # 开机（gui 显示窗口）
& $vmrun -T ws stop   <vmx> hard                       # 硬关机
& $vmrun -T ws reset  <vmx> hard                       # 硬重启
& $vmrun -T ws -gu user -gp pass runProgramInGuest <vmx> /bin/bash /tmp/x.sh
& $vmrun -T ws -gu user -gp pass copyFileFromHostToGuest <vmx> <本地> <客户机路径>
& $vmrun -T ws -gu user -gp pass copyFileFromGuestToHost <vmx> <客户机> <本地>
& $vmrun -T ws -gu user -gp pass captureScreen <vmx> <本地.png>
```

- **guest ops 需要 VMware Tools / open-vm-tools**。没装或客户机已挂，`captureScreen` 会一直挂着——务必给外部超时，别让它卡死整轮。
- `runProgramInGuest` 启动 GUI 程序会**立即返回**。要拿输出就让它写文件，再用 `copyFileFromGuestToHost` 取回。
- 客户机里跑 GUI 程序必须显式给环境：`DISPLAY=:0`、`XAUTHORITY=/home/<user>/.Xauthority`，否则程序静默退出，看起来像"命令没执行"。
- **硬关机可能把 Linux 客户机的 ext4 弄脏**，下次开机掉进 initramfs。处理顺序见 `references/troubleshooting.md`。
- 路径含中文时全部走 PowerShell，别在 bash 里拼。

### 5.5 客户机截图：在哪截比怎么截重要

| 方式 | 适用 | 代价 |
|---|---|---|
| 客户机内 `import -window root /tmp/a.png` | Linux 有 ImageMagick | 最干净，不受窗口缩放影响 |
| 客户机内 `xwd -root \| convert` | 无 `import` 时 | 同上 |
| 客户机内 PowerShell + `System.Drawing` | Windows 客户机 | 同上，需先加载程序集 |
| 主机 `vmrun captureScreen` | 有 Tools | 客户机挂了会挂起 |
| 主机抓 VMware 窗口 | 兜底 | 受 DPI、窗口遮挡、标题栏影响 |

留证类任务优先"客户机内截 + 拷回"，因为分辨率就是客户机真实分辨率，做报告时缩放比例稳定。

### 5.6 分辨率与窗口

- Linux：`xrandr --output Virtual1 --mode 1600x900`，**模式必须在列表里**，否则报 `cannot find mode`；先 `xrandr` 看可用模式。
- VMware 会按窗口大小自动回改分辨率，改完立刻截图确认，别假设它守住了。
- Windows 客户机改分辨率会弹"是否保留这些显示设置"，**12 秒不点自动回滚**。脚本要一次连发"应用 → 保留"，中间别停。VNC 会话在分辨率变化后尺寸可能不刷新，重连一次再截。
- 终端窗口类名别猜：Kali 2024 默认是 **qterminal**（不是 xfce4-terminal）。`xdotool search --class qterminal` 拿窗口 id，`windowsize/windowmove` 强设几何。qterminal 默认半透明，截图发灰，介意就改配置或用 `xterm`。

---

## 6. windows-mcp 用法要点

| 工具 | 关键参数 | 什么时候用 |
|---|---|---|
| `Snapshot` | `use_ui_tree=true`（默认）、`use_vision=true`、`use_annotation` | **每次动作前先调**，拿元素 label/id 与窗口状态 |
| `Screenshot` | `use_annotation`、`width/height_reference_line` | 只要画面、不要 UI 树时更快 |
| `Click` | `loc=[x,y]` 或 `label=`、`button`、`clicks`(0/1/2) | `clicks=0` 是纯悬停，用于展开菜单 |
| `Type` | `text`、`loc`/`label`、`clear`、`press_enter`、`caret_position` | 输入框清空重填用 `clear=true` |
| `Shortcut` | `shortcut="ctrl+s"` | 组合键，比逐键发稳 |
| `Scroll` | `loc`、`direction`、`wheel_times` | 1 次滚轮≈3-5 行 |
| `WaitFor` | `condition`、`text`、`window_name`、`timeout` | 代替 sleep，等界面就绪 |
| `App` | `mode=launch/launch_executable/resize/switch` | 启动、切换、调整窗口 |
| `Clipboard` | `mode=get/set` | 中文输入、长文本搬运 |
| `PowerShell` | `command`、`timeout` | 能走命令行就别点界面 |

组合范式：

```
Snapshot(use_ui_tree=true)  →  读 elements[].label / id  →  Click(label=N)
→  WaitFor(condition="text_exists", text="保存成功")  →  Snapshot 复核
```

- 元素有 `label` 就别用坐标；`label` 是整数 id，来自最近一次 Snapshot，**界面变了要重新 Snapshot**。
- 弹窗、保存对话框优先用 label，其次 `handle_dialog.py`（windows-control）的 `dismiss`/`click "确定"`。
- UAC 安全桌面、Ctrl+Alt+Del 界面：能截到图，但注入常被系统拦住。需要管理员权限的操作，改用"以管理员启动"或直接走 `PowerShell` 工具。

---

## 7. 常见任务配方

### 7.1 在虚拟机里做实验并逐步留证

```
1. 关机改 vmx 开 VNC → 开机 → Test-NetConnection 探端口
2. VNC 截图确认到达桌面/登录界面 → 登录（键盘或剪贴板）
3. 客户机内截图核对：确认分辨率、锁屏状态
4. 每个实验步骤：发命令 → 等待 → 客户机内截图 → 命名归档（stepNN_xxx.png）
5. 关键结论单独截一张（命中、报错、蓝屏、shell 提示符）
6. 事后在图上画红框，只框关键行，框要覆盖整行文字
```

留证的三个要求：时间顺序可追溯、关键信息可读、每张图能自解释（配一句图注）。

### 7.2 批量填表 / 连续点选

```
Snapshot → 读全部 label → 按 label 依次 Click + Type → 每 3~5 项 WaitFor 一次校验
```

- 表单里"下一步"按钮常常在滚动后移位，用 label 不要用坐标。
- 下拉框：先 Click 展开，再 WaitFor 选项文本出现，再点选项。
- 提交类按钮放在最后一步，且提交前截一张图留底。

### 7.3 跨应用搬运数据

```
应用 A 选中 → Shortcut("ctrl+c") → Clipboard(get) 读回文本
→ 需要清洗就用 Python 处理 → Clipboard(set) → 应用 B Shortcut("ctrl+v")
```

不要靠肉眼读屏幕抄数据；剪贴板拿到的才是原文。

### 7.4 无人值守的长流程

```
先关自动锁屏与屏保；每个阶段结束写一行日志；失败点保留现场截图；
全程只用一个入口脚本，出错可续跑
```

---

## 8. 故障速查

| 症状 | 最可能的原因 | 处理 |
|---|---|---|
| `vmrun` 报「未找到文件」但路径确实存在 | Git Bash 把 `/bin/bash` 改写成 `C:/Program Files/Git/bin/bash`，vmx 路径同时被改坏 | `export MSYS_NO_PATHCONV=1`；vmx 用 Windows 反斜杠路径，客机内路径保持 POSIX |
| 客户机内 `x11grab` / `import` 得到纯黑帧 | VMware 3D 加速开启时 X11 读回路径失效（`vmwgfx` 已加载） | vmx 加 `mks.enable3d = "FALSE"` 后重启；`vmrun captureScreen` 不受影响可先用来对照 |
| 密码正确却反复退回登录界面 | 系统里同时存在两个 X server，控制台停在 greeter 的 VT 上，会话其实还活着 | `loginctl list-sessions` 看 VTNr，`loginctl activate <id>` 切回，不必重启 |
| `SetForegroundWindow` 成功但按键全无反应 | 前台锁 + UIPI：目标进程权限更高时键盘注入被拦，鼠标有时能进 | 先发一次合成 ALT 解锁；跨权限场景直接换 VNC，不要在控制台注入上耗时间 |
| 对最大化窗口调用 `SW_RESTORE` 后录屏区域全错 | 它会把已最大化的窗口还原成小尺寸，固定裁切坐标随之失效 | 用 `GetWindowPlacement` 判断状态，只调 `SW_MAXIMIZE` |
| 点了没反应，光标却在动 | 首次点击只激活窗口 | 再点一次；或先 `App(switch)` 聚焦 |
| 列表项/图标被"打开"了 | 单击被识别成双击 | 检查是否重复发按下 |
| 单选按钮点不动 | 点在小圆圈边缘 | 点标签文字 |
| 截图大片黑块 | 长连接只收到增量帧 | 每帧缓存叠加，或每次重连取全帧 |
| 画面尺寸和客户机分辨率不一致 | 未申请 DesktopSize | 重连一次 |
| 请求帧缓冲一直超时 | `SetEncodings` 的 count 与编码数不符 | 修正报文头 |
| VNC 握手 EOF（0/4 字节） | 服务端设了密码而客户端没带 | 补密码；或服务端清空密码 |
| 主机光标锁死、SetCursorPos 返回 0 | 模态框或窗口 grab | 关模态框 → 重启 vmware 界面进程 |
| 客户机命令"没执行" | GUI 程序缺 DISPLAY/XAUTHORITY | 显式导出环境变量 |
| `captureScreen` 卡住不返回 | 客户机挂了 / 无 Tools | 外部超时 + 改用客户机内截图 |
| Linux 客户机开机进 initramfs | 硬关机导致根分区脏 | `fsck -y /dev/sda1` 后 `exit` |
| 中文输出乱码 | 代码页 936 vs UTF-8 | `chcp 65001` |
| 打中文全是问号/其他字符 | 键盘注入只有 keysym | 走剪贴板粘贴 |
| 分辨率改了又跳回去 | VMware 自动适配窗口 | 改完立即确认；必要时调窗口大小而非分辨率 |
| 文档被占用无法替换 | 编辑器/Word 仍持有句柄 | 先 `close_file`/退出 Word 再动文件 |
| 重连后打字打进了别的地方（甚至弹出启动器） | 新连接只建立了通道，**没有拿到焦点**；上一次会话关闭时窗口已失焦 | 每次重连后先 `click` 目标窗体内一个中性位置，再发按键；见 §4.4 |
| 第二次全量帧缓冲请求之后服务端不再回帧 | 连续两次 `FramebufferUpdateRequest(incremental=0)` 会被服务端合并/丢弃，客户端一直等 | 首帧全量，之后**只用增量**；无更新就沿用上一帧缓存，见 `scripts/vnclive.py` |
| 客户机一改分辨率 / 一崩溃，VNC 就断 | 帧缓冲尺寸变了，服务端主动断开 | 客户端必须自动重连（帧尺寸会变），并在重连后重新申请一次全量 |
| 画图里选了形状却画不出来 | 形状/颜色面板选完**不会自动关闭**，第一次点在画布上只是关面板 | 选完先发 `Esc` 关面板，再拖拽 |
| 录出来的屏幕视频进剪辑软件后"找不到帧" | `gdigrab` 输出是 VFR（常见 29.89fps），剪辑/合成按 30fps 算帧号就会越界 | 先转成严格 CFR 再用：`-fps_mode cfr -r 30 -g 30` |

更细的排查树见 `references/troubleshooting.md`。

---

## 9. 安全与边界

- 只操作**用户授权**的机器与窗口。VNC、Rebind 一律只监听回环地址。
- 破坏性操作（删除、格式化、批量改名、卸载、改注册表关键项）先说明影响并取得确认；删除走回收站，批量前先备份。
- 个人目录（桌面、下载、文档）默认**只读扫描**，不主动移动或删除。
- 截图里可能含密码、令牌、个人信息，存档前检查，不外传。
- 用完收尾：关掉临时开的 VNC 端口、停掉后台守护进程、把实验改过的配置列一份清单告诉用户（改了哪个 vmx、动了哪个系统目录），让用户决定是否还原。

---

## 10. 交付前自检

- [ ] 关键步骤都有截图，且截图能看清被指的要素（必要时红框标注）
- [ ] 每个动作后都有验证，没有"应该成功了"的假设
- [ ] 坐标来源可解释（UI 树 / 网格标注 / 元素 rect），不是拍脑袋
- [ ] 临时文件、后台进程、打开的端口已清理
- [ ] 对机器做过的改动已列清单交付
- [ ] 失败与绕行的地方如实记录，不粉饰

---

## 11. 随附脚本

| 脚本 | 作用 |
|---|---|
| `scripts/vnc_ctl.py` | VMware VNC 客户端：`size / shot / click x y [n] / rclick / drag / key / text`（`n=2` 即双击） |
| `scripts/des.py` | VNC 认证用纯 Python DES（含标准测试向量） |
| `scripts/vm_guest.py` | vmrun 封装：`exec/shot/put/get/list` |

```bash
cd ~/.workbuddy/skills/use-computer-pro/scripts
export VNC_PORT=5910 VNC_PASS=vkali

python vnc_ctl.py size
python vnc_ctl.py shot /tmp/a.png
python vnc_ctl.py click 400 300
python vnc_ctl.py click 400 300 2      # 双击
python vnc_ctl.py key "ctrl+alt+t"
python vnc_ctl.py text "ifconfig"
python vnc_ctl.py drag 100 100 500 400
```

```bash
python vm_guest.py --vmx "D:\vm\win7\win7.vmx" --gu user --gp pass exec --script ./task.sh
python vm_guest.py --vmx "..." --gu user --gp pass shot --out /tmp/guest.png --os linux
python vm_guest.py --vmx "..." --gu user --gp pass get  --remote /tmp/out.txt --local ./out.txt
```

细节与更多场景见 `references/troubleshooting.md`、`references/vmware-internals.md`。
