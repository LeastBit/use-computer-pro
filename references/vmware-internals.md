# VMware 控制通道细节

## 一、给虚拟机开 VNC

关机后编辑 `.vmx`，追加：

```
RemoteDisplay.vnc.enabled = "TRUE"
RemoteDisplay.vnc.port = "5910"
RemoteDisplay.vnc.password = "vkali"
```

| 项 | 说明 |
|---|---|
| `port` | 每个 VM 用不同端口，5910/5911/5912 依次递增 |
| `password` | **必须设**。留空时部分版本握手后直接断开；长度 ≤ 8，超出部分被忽略 |
| 生效时机 | 只在开机时读取，改完必须重启虚拟机 |
| 监听范围 | 默认仅本机回环。不要加 `RemoteDisplay.vnc.allowRemote`，也不要映射端口到公网 |
| 编码 | `.vmx` 用 ANSI 或 UTF-8 无 BOM；用 PowerShell `Set-Content -Encoding Default` 最稳 |

改完验证：

```powershell
Test-NetConnection 127.0.0.1 -Port 5910 -InformationLevel Quiet   # 期望 True
```

## 二、RFB 协议最小实现

```
S→C  "RFB 003.008\n"                     版本串，固定 12 字节
C→S  "RFB 003.008\n"
S→C  u8 安全类型数量 n；n × u8 类型列表   （3.3 版本则直接给 u32 类型）
C→S  u8 选定类型                          1=None，2=VNC 认证
     [类型 2] S→C 16 字节挑战；C→S 16 字节响应（DES-ECB 加密）
     S→C u32 认证结果，0 表示成功
C→S  u8 shared 标志                       1=共享会话
S→C  u16 宽、u16 高、16 字节像素格式、u32 名称长度、名称
```

像素格式 16 字节：`bpp, depth, big-endian, true-colour, r-max(u16), g-max(u16), b-max(u16), r-shift, g-shift, b-shift, 3 字节填充`。
**默认值就是 32bpp / depth 24 / shift 16-8-0 / 小端**，不主动 `SetPixelFormat` 最省事。

### 客户端消息

| 消息 | 结构 |
|---|---|
| SetPixelFormat | `u8=0, 3 字节填充, 16 字节格式` |
| SetEncodings | `u8=2, 1 字节填充, u16 编码数量, 数量 × i32 编码` |
| FramebufferUpdateRequest | `u8=3, u8 incremental, u16 x, u16 y, u16 w, u16 h` |
| KeyEvent | `u8=4, u8 down, 2 字节填充, u32 keysym` |
| PointerEvent | `u8=5, u8 button-mask, u16 x, u16 y` |

button-mask：bit0 左键、bit1 中键、bit2 右键。

### 两个致命细节

1. **`SetEncodings` 的编码数量必须与后面真正写的编码个数一致**。写 0 却追加两个 i32，服务器会静默丢弃整个连接后续请求，表现为"请求帧缓冲一直超时"——这个坑排查成本极高。
2. **`incremental=1` 时服务器只发变化区域**。自己实现客户端时若每帧都新建画布，会出现大片黑块；正确做法是缓存上一帧，只在收到的矩形上覆盖。

### 服务端消息

| 类型 | 结构 |
|---|---|
| 0 FramebufferUpdate | `u8=0, 1 字节填充, u16 矩形数, 每个: u16 x,y,w,h + i32 encoding + 数据` |
| 1 SetColourMapEntries | `u8=1, 1 字节填充, u16 起始, u16 数量, 数量 × 6 字节` |
| 2 Bell | `u8=2` |
| 3 ServerCutText | `u8=3, 3 字节填充, u32 长度, 文本` |

Raw 编码（encoding=0）的像素数据是 `w × h × 4` 字节，BGRX 顺序（第 0 字节蓝、第 1 字节绿、第 2 字节红）。

### 分辨率变化

客户机改分辨率后，服务端会发 `DesktopSize` 伪编码（-223）通知新尺寸。不申请该编码的客户端画面会停在旧尺寸，最省事的处理是**断开重连**。

## 三、vmrun 命令矩阵

```
vmrun -T ws <全局选项> <命令> <vmx> [参数...]
```

全局选项必须在命令之前：`-gu <用户> -gp <密码>`。

| 命令 | 用途 | 依赖 |
|---|---|---|
| `list` | 列出运行中的 VM | 无 |
| `start <vmx> [gui\|nogui]` | 开机 | 无 |
| `stop <vmx> [soft\|hard]` | 关机，优先 soft | 无 |
| `reset <vmx> [soft\|hard]` | 重启 | 无 |
| `runProgramInGuest <vmx> <exe> [args]` | 在客户机执行程序 | Tools |
| `copyFileFromHostToGuest <vmx> <本地> <客户机>` | 传文件进去 | Tools |
| `copyFileFromGuestToHost <vmx> <客户机> <本地>` | 取文件出来 | Tools |
| `captureScreen <vmx> <本地.png>` | 截屏 | Tools |
| `checkToolsState <vmx>` | 看 Tools 状态 | 无 |
| `listProcessesInGuest <vmx>` | 列客户机进程 | Tools |

### 使用要点

- **GUI 程序立即返回**。`runProgramInGuest` 不会等你，也不会带回 stdout。要结果就让目标程序写文件，再 `copyFileFromGuestToHost`。
- **客户机挂起时 `captureScreen` 会永久阻塞**。所有调用外层加超时（脚本里用 `subprocess.run(timeout=)`）。
- **Tools 未装**时，所有 guest 操作直接报错，`checkToolsState` 先确认。
- 路径含中文时，用 PowerShell 调用 vmrun，避免 bash 的编码转换。

### 推荐的"客户机执行"封装

```
1. 本地写脚本 task.sh
2. copyFileFromHostToGuest -> /tmp/agent_run.sh
3. 写 wrapper.sh：export DISPLAY/XAUTHORITY；/bin/bash /tmp/agent_run.sh > /tmp/agent_out.txt 2>&1；末尾追加 __rc=$?
4. runProgramInGuest /bin/bash wrapper.sh
5. copyFileFromGuestToHost /tmp/agent_out.txt -> 本地
```

好处：输出与退出码一起回来，GUI 环境变量不会漏，脚本失败也有痕迹。
`scripts/vm_guest.py exec` 已实现该流程。

## 四、客户机截图的四种做法

| 做法 | 命令 | 适用 | 注意 |
|---|---|---|---|
| ImageMagick 抓根窗口 | `DISPLAY=:0 import -window root /tmp/a.png` | Linux，最常用 | 锁屏/息屏会得到纯黑图 |
| xwd + convert | `xwd -root -silent \| convert xwd:- /tmp/a.png` | 无 `import` 时 | 同上 |
| PowerShell 截图 | `Add-Type System.Drawing; CopyFromScreen` | Windows | 需先加载 `System.Windows.Forms` 取屏幕尺寸 |
| vmrun captureScreen | `vmrun captureScreen` | 有 Tools、客户机健在 | 客户机挂起时阻塞 |

**判废标准**：图片模式为 `1`（1-bit），或整幅颜色数极少，说明没截到内容。

## 五、常见 vmx 相关坑

- **改 vmx 后忘了重启**：VNC 端口不监听，`ConnectionRefused`。
- **多台 VM 用同一端口**：后启动的抢不到端口，`Test-NetConnection` 仍为 True，但连上的是别的机器。用 `list` + 各自端口核对。
- **快照回滚后端口配置丢失**：快照只保存磁盘状态，配置以当前 vmx 为准；回滚后重新确认端口。
- **路径含空格/中文**：PowerShell 里用引号包裹整个路径，`&` 调用要放在引号外。
