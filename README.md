<div align="center">

<img src="assets/logo.png" width="120" alt="use-computer-pro" />

# use-computer-pro

**让 Agent 真正坐在电脑前 —— 一台，或者很多台。**

控制本机窗口，也控制机器里面跑着的虚拟机。看见屏幕、移动鼠标、点中元素、敲下文字，
并且每一步之后都回头确认：这件事真的发生了。

[![Skill](https://img.shields.io/badge/skill-SKILL.md-0020B8?style=flat-square)](SKILL.md)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20VMware-08B8A8?style=flat-square)](#通道选型)
[![Channels](https://img.shields.io/badge/channels-VNC%20%2B%20MCP-3a5bff?style=flat-square)](#通道选型)
[![License](https://img.shields.io/badge/license-MIT-0d1424?style=flat-square)](LICENSE)

</div>

---

## 它能做什么

不是"调用某个 API"，而是**代替一双手**：看屏幕、动鼠标、点按钮、打字、拖拽、截图留证。

**第一目标是你自己这台电脑** —— 大多数任务都发生在本机：填表、点软件、批量处理、抓图留证。
在此基础上，同一套原语可以延伸到 VMware 客户机，而且能同时驱动多台。
虚拟机不是前提，是需要时才用的第二类目标。

<p align="center">
  <img src="docs/preview.gif" width="820" alt="单机控制与双机协作演示" />
</p>

<p align="center">
  <a href="https://github.com/LeastBit/use-computer-pro/releases/tag/v1.0.0">
    <img src="https://img.shields.io/badge/%E2%96%B6%20%E5%AE%8C%E6%95%B4%E6%BC%94%E7%A4%BA%E7%89%87-99s%20%2F%201080p-0020B8?style=for-the-badge" alt="完整演示片" />
  </a>
</p>


## 通道选型

> **口诀**：能用 UI 树就不用坐标；能用客户机执行就不用模拟键盘；能用 VNC 就不用控制台。

| 场景 | 首选 | 备选 | 备注 |
|---|---|---|---|
| 本机 Windows 应用 | `windows-mcp` Snapshot + Click/Type | `windows-control` 脚本 | MCP 能拿到元素 label，比坐标稳 |
| 本机批量 / 脚本化 | `scripts/*.py` | MCP | 一次命令做一串动作更省调用 |
| 虚拟机里的客户机 | 客户机 VNC（键鼠 + 画面） | 控制台 + SendInput | 控制台注入极不稳定 |
| 客户机里跑命令 / 取文件 | `vmrun` guest ops | 客户机内起 HTTP 服务 | 需要 VMware Tools |
| 多台机器同屏 | noVNC 监控墙（`examples/wall`） | 多个 VNC 客户端 | VMware 多开只会变成标签页 |
| Linux 桌面 | `xdotool` + `import` | VNC | 见脚本说明 |

### 闭环

```
看见屏幕  →  决定动作  →  执行输入  →  再看一次
    ↑                                    │
    └────────── 不符合预期则重判 ←────────┘
```

硬性要求：**一个动作一次校验**。连续盲点三次以上，几乎一定是通道或坐标错了，停下来重判，不要靠加重试次数蒙过去。

---

## 快速开始

### 第一步：装 Windows-MCP（控制本机的主通道）

```bash
python --version            # 需要 3.14+
pip install uv
uvx windows-mcp serve       # 先单独跑通，首次启动慢属正常
```

写进 `~/.workbuddy/mcp.json`（**不是** `.mcp.json`；文件已存在就合并，别覆盖）：

```json
{
  "mcpServers": {
    "windows-mcp": { "command": "uvx", "args": ["windows-mcp", "serve"] }
  }
}
```

重启后在连接器管理的「自定义连接器」里点「信任」启用，`mcp__windows-mcp__*` 工具才会出现。

> 两个约束：`windows-mcp` 只支持 **Windows 10 / 11**（依赖 UI Automation 与 Python 3.14+），装在你自己的机器上；
> **虚拟机里的客户机不需要装它**，走 VNC 即可。

### 第二步：装技能与本地依赖

```bash
git clone https://github.com/LeastBit/use-computer-pro.git ~/.workbuddy/skills/use-computer-pro

pip install pyautogui pywinauto pygetwindow pillow numpy

# VNC 通道（客户机，先确认 vmx 里已配好端口与密码）
export VNC_PORT=5911 VNC_PASS=vkali
python scripts/vnc_ctl.py size          # 探到画面尺寸即表示通了
python scripts/vnc_ctl.py shot /tmp/a.png
python scripts/vnc_ctl.py click 400 300
python scripts/vnc_ctl.py drag 100 100 500 400

# 长连接采集（录屏 / 连续操作），首帧全量、之后增量
python scripts/vnclive.py
```

客户机侧如果装了 VMware Tools，`vmrun` 的 guest ops 通道最省事：

```bash
vmrun -T ws -gu kali -gp kali runProgramInGuest "<vmx>" /bin/uname -a
```

多机同屏 + 30fps 录制，见 [`examples/wall`](examples/wall)（noVNC + 一个三十行的 WebSocket↔TCP 桥）。

完整的环境前提、安装常见坑与自检清单，见 [`SKILL.md`](SKILL.md) 开头的「准备 · 先决条件与环境安装」。

---

## 仓库结构

```
SKILL.md                     方法论全文（12 节，含 60+ 条实测结论）
references/
  troubleshooting.md         排查树
  vmware-internals.md        RFB / VIX 协议细节
scripts/
  vnc_ctl.py                 单次 VNC 操作（shot / click / drag / key / text）
  vnclive.py                 长连接采集（增量帧 + 指针位置）
  local_fast.py              本机快路径（预读 + 坐标点击 + 画面哈希校验）
  bench_local.py             本机性能基准（复现上面的数字）
  vm_guest.py                vmrun 封装（exec / put / get / shot）
  des.py                     VNC 认证用的 DES（纯 Python）
examples/wall/               多机监控墙（noVNC + WebSocket→TCP 桥）
assets/logo.png
```


## 致谢

这套方法不是凭空长出来的，它站在这些项目与经验之上：

- [noVNC](https://github.com/novnc/noVNC) —— 浏览器里的 VNC 客户端，多机同屏的基础
- [windows-mcp](https://github.com/windows-mcp) —— 本机 UI 树与输入原语
- [pyautogui](https://github.com/asweigart/pyautogui) · [pywinauto](https://github.com/pywinauto/pywinauto) —— 本机输入注入与 UI Automation
- [Remotion](https://github.com/remotion-dev/remotion) · [FFmpeg](https://ffmpeg.org) —— 演示视频的合成与录制
- VMware VIX / RFB 协议文档 —— 虚拟机通道的全部依据

以及那些在真实机器上翻过的车：坐标偏 1.18 倍、VNC 握手 EOF、`SetEncodings` 静默挂起、
`mks.enable3d` 黑屏、重连丢焦点、VFR 找不到帧 —— 它们现在都是上面那张表里的一行。


---

## License

MIT © [LeastBit](https://github.com/LeastBit)
