# 多机监控墙

把三台（或更多）虚拟机的画面同时放到一个 1920×1080 的页面上，用 30fps 录屏就能直接当演示素材。

整套东西只有两个开源依赖：

- [noVNC](https://github.com/novnc/noVNC) —— 浏览器里的 VNC 客户端
- [ws](https://github.com/websockets/ws) —— 把 WebSocket 转成裸 TCP（等价于 websockify 的最小实现）

## 为什么不用 VMware 的多标签窗口

VMware Workstation 默认把多个虚拟机塞进同一个窗口的标签页，同一时刻只能看见一台；挂上 GUI 还会触发 open-vm-tools 的自动适应，把客户机分辨率改成窗口尺寸。noVNC 直读 VNC 流，不碰客户机显示配置。

## 跑起来

```bash
cd examples/wall
npm install                       # @novnc/novnc + ws
cp ../../assets/logo.png .        # 页面左上角的图标

# 1) WebSocket -> TCP 桥（端口映射写在 proxy.js 顶部）
node proxy.js

# 2) 静态服务
python -m http.server 8000

# 3) 浏览器打开
#    http://127.0.0.1:8000/index.html
```

客户机端要先在 `.vmx` 里开 VNC：

```ini
RemoteDisplay.vnc.enabled = "TRUE"
RemoteDisplay.vnc.port = "5911"
RemoteDisplay.vnc.password = "vkali"
```

`proxy.js` 默认映射 `6081→5911`、`6082→5910`、`6083→5912`，按需改。

## 页面上的两个细节

- **光标**：VMware 的 VNC 服务端不把指针画进帧缓冲，所以页面读 `cursors.json` 自己贴一个箭头。驱动脚本每次发 `PointerEvent` 时写一次坐标，页面按 `guest → 窗格` 的比例映射。
- **布局**：页面固定 1920×1080，浏览器用 `--kiosk` 打开后从屏幕左上角 `(0,0)` 录制 `1920x1080` 区域，录下来就是成片画幅，不用再裁。

```bash
ffmpeg -f gdigrab -framerate 30 -offset_x 0 -offset_y 0 \
       -video_size 1920x1080 -draw_mouse 0 -i desktop \
       -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p out.mp4
```

> `-draw_mouse 0` 很关键：否则宿主机的鼠标会压在画面上，而客户机里的光标其实是在窗格内部的。
