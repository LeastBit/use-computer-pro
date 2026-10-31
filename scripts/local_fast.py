# -*- coding: utf-8 -*-
"""本机快速操作层（Fast path for local Windows control）

实测结论（Windows 11 / 2560x1600）：
    pyautogui.click 默认 PAUSE=0.1    →  107 ms/次
    pyautogui.click PAUSE=0           →    1 ms/次
    UIA 元素 .click_input()           →  475 ms/次   ← 慢在属性读取与内部等待
    UIA 元素 .rectangle()             →   83 ms/次
    pyautogui 按缓存坐标点击          →  0.9 ms/次

所以策略只有一条：**UIA 只用来「找」，找到后缓存屏幕坐标，点击一律走坐标。**

用法：
    import local_fast as lf
    lf.setup()
    w = lf.win("记事本")
    lf.click(w, "文件")          # 首次约 150-200ms（要查元素），之后 ~1ms
    lf.type("hello")
"""
from __future__ import annotations

import ctypes
import hashlib
import time
from typing import Optional, Sequence

import pyautogui
from PIL import ImageGrab
from pywinauto import Desktop

pyautogui.FAILSAFE = False

_User32 = ctypes.windll.user32

_WIN_CACHE: dict[str, tuple] = {}      # key -> (hwnd, wrapper)
_HANDLE: dict[int, int] = {}           # id(wrapper) -> hwnd
_POS: dict[tuple, tuple] = {}          # (hwnd, name, ctype) -> (x, y, win_rect)
_PRIMED: dict[int, tuple] = {}         # hwnd -> (win_rect, {name: (x, y)})


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _hwnd(w) -> int:
    k = id(w)
    if k not in _HANDLE:
        _HANDLE[k] = w.handle
    return _HANDLE[k]


def _alive(hwnd: int) -> bool:
    try:
        return bool(_User32.IsWindow(hwnd))
    except Exception:
        return False


def _win_rect(hwnd: int) -> tuple:
    r = _RECT()
    _User32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)


def setup(pause: float = 0.0, failsafe: bool = False) -> None:
    """必须先调。默认每次动作停 0.1 秒，是最大的隐形成本。"""
    pyautogui.PAUSE = pause
    pyautogui.FAILSAFE = failsafe


def win(title_re: str, backend: str = "uia", timeout: float = 5.0, use_cache: bool = True):
    """取窗口。命中缓存约 0.05ms（用 IsWindow 校验，不做 UIA 查询）。"""
    key = f"{backend}:{title_re}"
    if use_cache and key in _WIN_CACHE:
        hwnd, w = _WIN_CACHE[key]
        if _alive(hwnd):
            return w

    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            w = Desktop(backend=backend).window(title_re=title_re, visible_only=True)
            if w.exists(timeout=0.2):
                hwnd = w.handle
                _WIN_CACHE[key] = (hwnd, w)
                _HANDLE[id(w)] = hwnd
                return w
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(0.05)
    raise TimeoutError(f"找不到窗口 {title_re}: {last}")


def invalidate(w=None) -> None:
    """界面结构或窗口位置变化后清缓存。"""
    if w is None:
        _WIN_CACHE.clear()
        _POS.clear()
        _PRIMED.clear()
        _HANDLE.clear()
        return
    hwnd = _hwnd(w)
    _PRIMED.pop(hwnd, None)
    for k in [k for k in _POS if k[0] == hwnd]:
        _POS.pop(k, None)


def element(w, name: str, control_type: Optional[str] = None):
    """语义查找：返回 UIA 元素。一次约 120ms。"""
    kwargs = {"title": name}
    if control_type:
        kwargs["control_type"] = control_type
    try:
        el = w.child_window(**kwargs)
        return el if el.exists(timeout=0.3) else None
    except Exception:
        return None


def elements(w, control_type: Optional[str] = None, limit: int = 400):
    """整树枚举，约 90-120ms。看全貌时用，别放进循环。"""
    if control_type:
        return w.descendants(control_type=control_type)[:limit]
    return w.descendants()[:limit]


def prime(w, force: bool = False) -> dict:
    """一次性把整窗元素的「名字 -> 屏幕坐标」读进内存。

    实测 56 个节点：枚举 112ms + 读名字 14ms + 读矩形 18ms ≈ 144ms，
    之后每次命中都是本地字典查找。要在一个窗口里连点多个元素时，先调它。
    """
    hwnd = _hwnd(w)
    wr = _win_rect(hwnd)
    if not force and hwnd in _PRIMED and _PRIMED[hwnd][0] == wr:
        return _PRIMED[hwnd][1]

    table: dict[str, tuple] = {}
    try:
        for e in w.descendants():
            try:
                t = e.window_text()
                if not t or t in table:
                    continue
                r = e.rectangle()
                table[t] = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            except Exception:
                continue
    except Exception:
        pass
    _PRIMED[hwnd] = (wr, table)
    return table


def pos(w, name: str, control_type: Optional[str] = None, use_cache: bool = True):
    """元素中心的屏幕坐标。命中约 0.01ms；窗口移动过会自动失效。"""
    hwnd = _hwnd(w)
    key = (hwnd, name, control_type)
    wr = _win_rect(hwnd)

    if use_cache and key in _POS:
        x, y, wr0 = _POS[key]
        if wr0 == wr:
            return (x, y)

    # 先查整树预读表（本地字典，0 成本）
    if use_cache and hwnd in _PRIMED:
        wr0, table = _PRIMED[hwnd]
        if wr0 == wr and name in table:
            return table[name]

    el = element(w, name, control_type)
    if el is None:
        return None
    r = el.rectangle()
    p = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    _POS[key] = (p[0], p[1], wr)
    return p


def click(w, target, button: str = "left", clicks: int = 1) -> bool:
    """target 为元素名或坐标。元素名只用于定位，实际按坐标点击（0.9ms）。"""
    if isinstance(target, (tuple, list)):
        pyautogui.click(target[0], target[1], button=button, clicks=clicks)
        return True

    p = pos(w, target)
    if p is None:
        return False
    pyautogui.click(p[0], p[1], button=button, clicks=clicks)
    return True


def hover(w, target) -> bool:
    p = target if isinstance(target, (tuple, list)) else pos(w, target)
    if p is None:
        return False
    pyautogui.moveTo(p[0], p[1])
    return True


def type_text(text: str, interval: float = 0.0) -> None:
    """整串输入，约 0.5ms/字符。逐字符 press 更慢且更易丢键。"""
    pyautogui.write(text, interval=interval)


def hotkey(*keys: str) -> None:
    pyautogui.hotkey(*keys)


def press(key: str) -> None:
    pyautogui.press(key)


def grab(window=None, region: Optional[Sequence[int]] = None):
    """窗口级截图优先：比全屏快，且不受其它窗口遮挡干扰。"""
    if region is not None:
        return ImageGrab.grab(bbox=tuple(region))
    if window is not None:
        try:
            return ImageGrab.grab(window=_hwnd(window))
        except TypeError:
            pass
    return ImageGrab.grab()


def digest(img) -> str:
    """把图压成 64x40 灰度哈希，用于判断"画面有没有变"。"""
    return hashlib.md5(img.convert("L").resize((64, 40)).tobytes()).hexdigest()


def wait_change(window=None, region=None, timeout: float = 3.0,
                interval: float = 0.06, baseline: Optional[str] = None) -> bool:
    """等画面变化。替代 sleep —— 变化一到就返回，通常省一半以上等待。"""
    base = baseline or digest(grab(window, region))
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        if digest(grab(window, region)) != base:
            return True
    return False


def wait_stable(window=None, region=None, timeout: float = 3.0,
                interval: float = 0.06, stable_times: int = 2) -> bool:
    """等画面稳定（连续 N 次一致），用于等动画/加载结束。"""
    prev = digest(grab(window, region))
    same = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        cur = digest(grab(window, region))
        same = same + 1 if cur == prev else 0
        if same >= stable_times:
            return True
        prev = cur
    return False


def save(path: str, window=None, region=None) -> str:
    grab(window, region).save(path)
    return path
