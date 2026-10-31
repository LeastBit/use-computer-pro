# -*- coding: utf-8 -*-
"""长连接 VNC 采集器 —— 为录制准备

比 vnc_ctl.py 多的能力:
  * 持久连接, 支持增量更新 (录屏必须)
  * 正确处理 ServerCutText (1+3+4+payload), 这是之前超时的根因
  * 记录指针位置, 供后期绘制合成光标
"""
import os, socket, struct, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import des  # noqa: E402

KEYSYMS = {
    "enter": 0xFF0D, "esc": 0xFF1B, "tab": 0xFF09, "backspace": 0xFF08,
    "delete": 0xFFFF, "win": 0xFFEB, "ctrl": 0xFFE3, "alt": 0xFFE9,
    "shift": 0xFFE1, "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
    "space": 0x20,
}
for _i in range(1, 13):
    KEYSYMS["f%d" % _i] = 0xFFBE + _i - 1
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    KEYSYMS[_c] = ord(_c)
for _c, _k in {".": 0x2E, ",": 0x2C, "/": 0x2F, "-": 0x2D, "=": 0x3D, ":": 0x3A,
               ";": 0x3B, "|": 0x7C, "_": 0x5F, '"': 0x22, "'": 0x27, " ": 0x20,
               "\\": 0x5C, "(": 0x28, ")": 0x29, "&": 0x26, "*": 0x2A,
               "$": 0x24, "#": 0x23, "@": 0x40, "!": 0x21, "?": 0x3F}.items():
    KEYSYMS.setdefault(_c, _k)


class Show:
    def __init__(self, port, password="vkali", host="127.0.0.1"):
        self.s = socket.create_connection((host, port), timeout=10)
        self.s.settimeout(8)
        self.sets = 0
        self._handshake(password)
        self.fb = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.cx, self.cy = self.w // 2, self.h // 2
        self.dirty = False

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise EOFError("closed")
            buf += c
        return buf

    def _handshake(self, pw):
        b = self._recv(12)
        if b[:7] == b"RFB 003." and b[7:11] >= b"0038":
            self.s.sendall(b"RFB 003.008\n")
            n = self._recv(1)[0]
            types = list(self._recv(n))
            if 2 in types and pw:
                self.s.sendall(bytes([2]))
                ch = self._recv(16)
                self.s.sendall(des.des_ecb(des.vnc_key(pw), ch))
            elif 1 in types:
                self.s.sendall(bytes([1]))
            else:
                raise RuntimeError("no auth type %r" % types)
            res = self._recv(4)
        else:
            self.s.sendall(b"RFB 003.003\n")
            sec = struct.unpack(">I", self._recv(4))[0]
            if sec == 2:
                ch = self._recv(16)
                self.s.sendall(des.des_ecb(des.vnc_key(pw), ch))
                res = self._recv(4)
            elif sec == 1:
                res = b"\0\0\0\0"
            else:
                raise RuntimeError("sec %d" % sec)
        if res != b"\0\0\0\0":
            raise RuntimeError("auth failed")
        self.s.sendall(bytes([1]))
        self.w, self.h = struct.unpack(">HH", self._recv(4))
        self._recv(16)
        nl = struct.unpack(">I", self._recv(4))[0]
        self._recv(nl)

    # ---------- 画面 ----------
    def request(self, incremental=True):
        self.s.sendall(struct.pack(">BBHHHH", 3, 1 if incremental else 0, 0, 0, self.w, self.h))

    def pump(self, deadline):
        """读取一条服务器消息并应用; 返回 'update' / 'other' / None(超时)"""
        try:
            mt = self._recv(1)[0]
        except (socket.timeout, TimeoutError):
            return None
        if mt == 0:
            self._recv(1)
            n = struct.unpack(">H", self._recv(2))[0]
            for _ in range(n):
                x, y, w, h, enc = struct.unpack(">HHHHi", self._recv(12))
                if enc != 0:
                    raise RuntimeError("enc %d" % enc)
                d = np.frombuffer(self._recv(w * h * 4), dtype=np.uint8)
                self.fb[y:y + h, x:x + w] = d.reshape(h, w, 4)[:, :, [2, 1, 0]]
            self.sets += 1
            self.dirty = True
            return "update"
        if mt == 1:                      # SetColourMapEntries
            self._recv(3)
            n = struct.unpack(">H", self._recv(2))[0]
            self._recv(6 * n)
            return "other"
        if mt == 2:                      # Bell
            return "other"
        if mt == 3:                      # ServerCutText: 1 + 3 pad + 4 len + text
            self._recv(3)
            ln = struct.unpack(">I", self._recv(4))[0]
            if ln:
                self._recv(ln)
            return "other"
        raise RuntimeError("server msg %d" % mt)

    def grab(self, full=False, timeout=4.0):
        """full=True 必须拿到全帧; 否则超时即视为无变化, 沿用上一帧"""
        self.request(incremental=not full)
        end = time.time() + timeout
        while time.time() < end:
            r = self.pump(end)
            if r == "update":
                return self.fb, True
        if full:
            raise TimeoutError("no full frame in %.1fs (port %s)" % (timeout, self.w))
        return self.fb, False

    # ---------- 输入 ----------
    def pointer(self, x, y, mask=0):
        self.cx, self.cy = int(x), int(y)
        self.s.sendall(struct.pack(">BBHH", 5, mask, int(x), int(y)))

    def click(self, x, y, n=1, right=False):
        mask = 4 if right else 1
        self.pointer(x, y, 0)
        time.sleep(0.05)
        for _ in range(max(1, n)):
            self.pointer(x, y, mask)
            time.sleep(0.05)
            self.pointer(x, y, 0)
            time.sleep(0.06)

    def key(self, ks, down):
        self.s.sendall(struct.pack(">BBxxI", 4, 1 if down else 0, ks))

    def keys(self, spec, gap=0.05):
        for combo in spec.split(" "):
            codes = [KEYSYMS[p] for p in combo.split("+")]
            for k in codes:
                self.key(k, 1)
                time.sleep(0.02)
            for k in reversed(codes):
                self.key(k, 0)
                time.sleep(0.02)
            time.sleep(gap)

    def text(self, s, cps=0.045):
        """逐字输入, 默认 22 字/秒, 模拟真实手速

        注意: VNC 发的是 keysym 而不是字符. 对于 US 布局上需要 Shift 的符号,
        必须真的按下 Shift, 否则服务端会把 ':' 变成 ';'、'|' 变成 '\\'.
        """
        SHIFTED = set('~!@#$%^&*()_+{}|:"<>?')
        for ch in s:
            if ch == "\n":
                self.keys("enter")
                continue
            ks = KEYSYMS.get(ch, ord(ch))
            shift = ch.isupper() or ch in SHIFTED
            if shift:
                self.key(KEYSYMS["shift"], 1)
                time.sleep(0.01)
            self.key(ks, 1)
            time.sleep(0.012)
            self.key(ks, 0)
            time.sleep(0.012)
            if shift:
                self.key(KEYSYMS["shift"], 0)
                time.sleep(0.01)
            time.sleep(max(0.005, cps - 0.034))


if __name__ == "__main__":
    for p in (5911, 5910, 5912):
        s = Show(p)
        t = time.time()
        for i in range(4):
            s.grab()
        print(f"port {p} {s.w}x{s.h}  4帧耗时 {time.time()-t:.2f}s  "
              f"({'%.1f fps' % (4/(time.time()-t))}) sets={s.sets}")
