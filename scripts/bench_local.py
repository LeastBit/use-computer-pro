# -*- coding: utf-8 -*-
"""本机操作性能基准

用途：在自己机器上复现 SKILL.md「12. 性能」里的数字，不要照抄别处的结论。
运行：
    python scripts/bench_local.py

只做测量，不改动系统设置（pyautogui.PAUSE 仅在本进程内生效）。
"""
import time
import statistics as st

import pyautogui
from PIL import ImageGrab
from pywinauto import Desktop


def ms(fn, n=5, warmup=1):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t) * 1000)
    return st.median(ts), min(ts), max(ts)


def main():
    print("=" * 62)
    print("本机操作性能基准")
    print("=" * 62)

    # 1) 输入：pyautogui 默认每次动作后停 0.1 秒
    orig_pause = pyautogui.PAUSE
    pyautogui.FAILSAFE = False
    r_default, _, _ = ms(lambda: pyautogui.click(600, 400), n=5, warmup=0)
    pyautogui.PAUSE = 0
    r_zero, r_min, r_max = ms(lambda: pyautogui.click(600, 400))
    pyautogui.PAUSE = orig_pause

    print("\n[输入]")
    print(f"  click  PAUSE=0.1(默认)   {r_default:7.1f} ms")
    print(f"  click  PAUSE=0           {r_zero:7.1f} ms   (min {r_min:.1f} / max {r_max:.1f})")
    print(f"  → 单次动作差 {r_default - r_zero:.0f} ms，100 次动作差 {(r_default - r_zero) * 100 / 1000:.1f} s")

    pyautogui.PAUSE = 0
    text = "hello world 12345"
    t = time.perf_counter()
    pyautogui.write(text, interval=0)
    t_write = (time.perf_counter() - t) * 1000
    print(f"  write  {len(text)} 字符        {t_write:7.1f} ms  ({t_write / len(text):.1f} ms/字符)")
    pyautogui.PAUSE = orig_pause

    # 2) 截图
    print("\n[截图]")
    f_full, _, _ = ms(lambda: ImageGrab.grab(), n=3)
    f_reg, _, _ = ms(lambda: ImageGrab.grab(bbox=(0, 0, 640, 480)), n=3)
    w, h = ImageGrab.grab().size
    print(f"  ImageGrab 全屏 {w}x{h}   {f_full:7.1f} ms")
    print(f"  ImageGrab 区域 640x480    {f_reg:7.1f} ms")
    print("  → 区域截图省得不多，真正的开销在抓屏本身；需要更快可换 mss")

    # 3) UI 树（等价于一次 Snapshot）
    print("\n[UI 树]")
    u_list, _, _ = ms(lambda: Desktop(backend="uia").windows(), n=3)
    w_list, _, _ = ms(lambda: Desktop(backend="win32").windows(), n=3)
    n_u = len(Desktop(backend="uia").windows())
    n_w = len(Desktop(backend="win32").windows())
    print(f"  uia   枚举顶层 {n_u:3d} 个      {u_list:7.1f} ms")
    print(f"  win32 枚举顶层 {n_w:3d} 个      {w_list:7.1f} ms")

    wins = Desktop(backend="uia").windows(visible_only=True)
    target = max(wins, key=lambda x: len(x.window_text() or ""))
    tree, _, _ = ms(lambda: target.descendants(), n=3)
    print(f"  uia   全树 {len(target.descendants()):3d} 节点      {tree:7.1f} ms   ← 一次 Snapshot 的量级")

    # 4) 典型循环
    print("\n[典型「动作 + 校验」循环]")
    naive = u_list + r_default + u_list + f_full
    fast = r_zero + f_reg
    print(f"  朴素写法  截图/快照 + 点击(默认) + 再快照 + 再截图  ≈ {naive:6.0f} ms/步")
    print(f"  优化写法  缓存元素 + 点击(PAUSE=0) + 区域校验       ≈ {fast:6.0f} ms/步")
    print(f"  → 约 {naive / fast:.1f}x 提速；20 步的任务差 {(naive - fast) * 20 / 1000:.1f} s")


if __name__ == "__main__":
    main()
