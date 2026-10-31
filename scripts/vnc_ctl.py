# -*- coding: utf-8 -*-
"""Minimal VMware-VNC controller (RFB 3.3 / 3.8, VNC or None auth).

Usage:
  set VNC_PORT=5910 & set VNC_PASS=vkali
  python vnc_ctl.py size
  python vnc_ctl.py shot  out.png
  python vnc_ctl.py click 400 300
  python vnc_ctl.py click 400 300 2          # double click (same sequence)
  python vnc_ctl.py rclick 400 300
  python vnc_ctl.py drag 100 100 500 400
  python vnc_ctl.py key "ctrl+alt+t"
  python vnc_ctl.py text "ifconfig"

Env: VNC_HOST (default 127.0.0.1), VNC_PORT (default 5910), VNC_PASS (default empty)

Design notes (learned the hard way):
  * one connection per invocation -> every shot is a full frame, no stale regions
  * a single click sends exactly one press/release (two presses = double click)
  * SetEncodings is optional; if you send it, the count field MUST match
"""
import os, socket, struct, sys, time
from PIL import Image

HOST = os.environ.get("VNC_HOST", "127.0.0.1")
PORT = int(os.environ.get("VNC_PORT", "5910"))
PASSWORD = os.environ.get("VNC_PASS", "")

KEYSYMS = {
    "enter": 0xFF0D, "esc": 0xFF1B, "tab": 0xFF09, "backspace": 0xFF08,
    "delete": 0xFFFF, "win": 0xFFEB, "ctrl": 0xFFE3, "alt": 0xFFE9,
    "shift": 0xFFE1, "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
    "insert": 0xFF63, "home": 0xFF50, "end": 0xFF57, "pageup": 0xFF55, "pagedown": 0xFF56,
    "space": 0x20, "menu": 0xFF67,
}
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    KEYSYMS[_c] = ord(_c)
for _c, _k in {'.': 0x2E, ',': 0x2C, '/': 0x2F, '-': 0x2D, '=': 0x3D, ' ': 0x20,
               ':': 0x3A, ';': 0x3B, '\\': 0x5C, '_': 0x5F, '|': 0x7C,
               '(': 0x28, ')': 0x29, '"': 0x22, "'": 0x27,
               '!': 0x21, '@': 0x40, '#': 0x23, '$': 0x24, '%': 0x25,
               '^': 0x5E, '&': 0x26, '*': 0x2A, '+': 0x2B, '{': 0x7B,
               '}': 0x7D, '<': 0x3C, '>': 0x3E, '?': 0x3F, '~': 0x7E}.items():
    KEYSYMS.setdefault(_c, _k)
for _i in range(1, 13):
    KEYSYMS["f%d" % _i] = 0xFFBE + (_i - 1)


class VNC:
    def __init__(self, host=HOST, port=PORT, password=PASSWORD):
        self.s = socket.create_connection((host, port), timeout=20)
        self.s.settimeout(25)
        self.handshake(password)

    def recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise EOFError("connection closed, got %d/%d bytes" % (len(buf), n))
            buf += chunk
        return buf

    def handshake(self, password):
        banner = self.recv(12)
        if not banner.startswith(b"RFB"):
            raise RuntimeError("not a VNC server: %r" % banner)
        if banner[:7] == b"RFB 003." and banner[7:11] >= b"0038":
            self.s.sendall(b"RFB 003.008\n")
            n = self.recv(1)[0]
            types = list(self.recv(n))
            if 2 in types and password:
                self.s.sendall(bytes([2]))
                challenge = self.recv(16)
                import des
                self.s.sendall(des.des_ecb(des.vnc_key(password), challenge))
            elif 1 in types:
                self.s.sendall(bytes([1]))
            else:
                raise RuntimeError("no usable security type: %r" % types)
            res = self.recv(4)
        else:
            self.s.sendall(b"RFB 003.003\n")
            sec = struct.unpack(">I", self.recv(4))[0]
            if sec == 2:
                challenge = self.recv(16)
                import des
                self.s.sendall(des.des_ecb(des.vnc_key(password), challenge))
                res = self.recv(4)
            elif sec == 1:
                res = b"\x00\x00\x00\x00"
            else:
                raise RuntimeError("unsupported security type %d" % sec)
        if res != b"\x00\x00\x00\x00":
            raise RuntimeError("authentication failed")
        self.s.sendall(bytes([1]))                     # ClientInit: shared
        self.w, self.h = struct.unpack(">HH", self.recv(4))
        self.recv(16)                                   # server pixel format
        nlen = struct.unpack(">I", self.recv(4))[0]
        self.recv(nlen)                                 # desktop name
        # keep the default 32bpp / shift 16-8-0 format; no SetPixelFormat needed

    # ---- input -------------------------------------------------------------
    def pointer(self, x, y, mask):
        self.s.sendall(struct.pack(">BBHH", 5, mask, int(x), int(y)))

    def move(self, x, y):
        self.pointer(x, y, 0)
        time.sleep(0.08)

    def click(self, x, y, n=1, right=False):
        """n presses in one sequence: 1 = click, 2 = double click."""
        mask = 4 if right else 1
        self.move(x, y)
        for _ in range(max(1, n)):
            self.pointer(x, y, mask)
            time.sleep(0.06)
            self.pointer(x, y, 0)
            time.sleep(0.10 if n > 1 else 0.0)

    def drag(self, x1, y1, x2, y2, steps=12):
        mask = 1
        self.move(x1, y1)
        self.pointer(x1, y1, mask)
        time.sleep(0.12)
        for i in range(1, steps + 1):
            self.pointer(x1 + (x2 - x1) * i // steps, y1 + (y2 - y1) * i // steps, mask)
            time.sleep(0.03)
        time.sleep(0.08)
        self.pointer(x2, y2, 0)
        time.sleep(0.10)

    def key(self, ks, down):
        self.s.sendall(struct.pack(">BBxxI", 4, 1 if down else 0, ks))

    def send_keys(self, spec):
        for combo in spec.split(" "):
            codes = [KEYSYMS[p] for p in combo.split("+")]   # resolve before pressing
            for k in codes:
                self.key(k, 1); time.sleep(0.03)
            for k in reversed(codes):
                self.key(k, 0); time.sleep(0.03)
            time.sleep(0.15)

    def send_text(self, s):
        for ch in s:
            if ch == "\n":
                self.send_keys("enter")
                continue
            ks = KEYSYMS.get(ch, ord(ch))
            shift = ch.isupper() or ch in '!@#$%^&*()_+{}|:"<>?~'
            if shift:
                self.key(KEYSYMS["shift"], 1); time.sleep(0.02)
            self.key(ks, 1); time.sleep(0.02)
            self.key(ks, 0); time.sleep(0.02)
            if shift:
                self.key(KEYSYMS["shift"], 0); time.sleep(0.02)

    # ---- framebuffer -------------------------------------------------------
    def fb(self):
        self.s.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, self.w, self.h))
        img = Image.new("RGB", (self.w, self.h))
        px = img.load()
        while True:
            mt = self.recv(1)[0]
            if mt == 0:
                self.recv(1)
                n = struct.unpack(">H", self.recv(2))[0]
                for _ in range(n):
                    x, y, w, h, enc = struct.unpack(">HHHHi", self.recv(12))
                    if enc != 0:
                        raise RuntimeError("unsupported encoding %d (request Raw only)" % enc)
                    data = self.recv(w * h * 4)
                    for row in range(h):
                        base = row * w * 4
                        for col in range(w):
                            i = base + col * 4
                            px[x + col, y + row] = (data[i + 2], data[i + 1], data[i])
                return img
            elif mt == 1:      # SetColourMapEntries
                self.recv(3)
            elif mt == 2:      # Bell
                self.recv(1)
            elif mt == 3:      # ServerCutText
                self.recv(7)
            else:
                raise RuntimeError("unknown server message %d" % mt)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1].lower()
    v = VNC()
    if cmd == "size":
        print(v.w, v.h)
    elif cmd == "shot":
        out = sys.argv[2] if len(sys.argv) > 2 else "shot.png"
        v.fb().save(out)
        print("%s %dx%d" % (out, v.w, v.h))
    elif cmd == "click":
        v.click(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 1)
        print("ok")
    elif cmd == "rclick":
        v.click(int(sys.argv[2]), int(sys.argv[3]), 1, right=True)
        print("ok")
    elif cmd == "drag":
        v.drag(*[int(a) for a in sys.argv[2:6]])
        print("ok")
    elif cmd == "key":
        v.send_keys(sys.argv[2])
        print("ok")
    elif cmd == "text":
        v.send_text(sys.argv[2])
        print("ok")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
