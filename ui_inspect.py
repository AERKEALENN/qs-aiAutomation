#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui_inspect.py - 通过 Windows UI Automation API 枚举桌面控件，
输出文本清单，并生成一张用序号标注所有控件的图片。

依赖：
    pip install uiautomation pyautogui Pillow

用法：
    python ui_inspect.py
"""

import os
import sys
import time
import pyautogui
from PIL import Image, ImageDraw, ImageFont
import uiautomation as auto

SCREEN_W, SCREEN_H = pyautogui.size()

MIN_SIZE = 8

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sanitize(s):
    return "".join(ch for ch in (s or "") if ch.isprintable() and ch not in "\u200e\u200f")


def collect_controls():
    """遍历整个桌面控件树，返回所有可见且有意义的控件。"""
    root = auto.GetRootControl()
    found = []
    seen = set()

    def walk(ctrl, depth, ancestor_min=False):
        left = top = right = bottom = 0
        try:
            r = ctrl.BoundingRectangle
            if r is not None:
                left, top, right, bottom = r.left, r.top, r.right, r.bottom
        except Exception:
            r = None
        w = right - left
        h = bottom - top

        name = "" if not hasattr(ctrl, "Name") else (ctrl.Name or "")
        cls = "" if not hasattr(ctrl, "ClassName") else (ctrl.ClassName or "")
        ctype = "" if not hasattr(ctrl, "ControlTypeName") else (ctrl.ControlTypeName or "")
        aid = "" if not hasattr(ctrl, "AutomationId") else (ctrl.AutomationId or "")

        # 检测最小化窗口（坐标落入经典 -32000 区域）
        minimized = ancestor_min
        if ctype == "WindowControl" and r is not None and (top <= -30000 or left <= -30000):
            minimized = True

        if (not minimized) and r is not None and w >= MIN_SIZE and h >= MIN_SIZE:
            try:
                offscreen = ctrl.IsOffscreen
            except Exception:
                offscreen = False
            on_screen = (right > 0 and bottom > 0 and
                         left < SCREEN_W and top < SCREEN_H)
            if offscreen or not on_screen:
                pass
            else:
                key = (round(left), round(top), round(right), round(bottom), name, cls)
                if key not in seen:
                    seen.add(key)
                    found.append({
                        "name": name,
                        "class": cls,
                        "type": ctype,
                        "aid": aid,
                        "rect": (int(left), int(top), int(right), int(bottom)),
                        "w": int(w),
                        "h": int(h),
                        "ctrl": ctrl,
                    })

        if depth < 30:
            try:
                children = ctrl.GetChildren()
            except Exception:
                children = []
            for child in children:
                walk(child, depth + 1, minimized)

    walk(root, 0)
    return found


def filter_large(controls):
    """丢弃面积超过屏幕 20% 的控件（桌面/全屏背景等）。"""
    limit = 0.20 * SCREEN_W * SCREEN_H
    return [c for c in controls if c["w"] * c["h"] <= limit]


def filter_oversized(controls, limit=450):
    """丢弃长或宽超过 limit 像素的控件（细长的标题栏/侧边栏等）。"""
    return [c for c in controls if c["w"] <= limit and c["h"] <= limit]


def filter_occluded(controls):
    """用 ControlFromPoint 做真实可见性测试：中心点被其它控件挡住则丢弃。"""
    kept = []
    for c in controls:
        left, top, right, bottom = c["rect"]
        cx, cy = (left + right) // 2, (top + bottom) // 2
        try:
            hit = auto.ControlFromPoint(cx, cy)
        except Exception:
            hit = None
        if hit is None:
            kept.append(c)
            continue
        try:
            my_rid = c["ctrl"].GetRuntimeId()
            hit_rid = hit.GetRuntimeId()
        except Exception:
            kept.append(c)
            continue
        # 命中点在我们的控件上，当且仅当：
        # 命中控件就是我们的控件/后代（向上找能得到我们），或
        # 我们的控件是命中控件的后代（向上找能得到命中控件）
        visible = False
        try:
            node = hit
            for _ in range(25):
                if node is None:
                    break
                if node.GetRuntimeId() == my_rid:
                    visible = True
                    break
                node = node.GetParentControl()
        except Exception:
            visible = True
        if not visible:
            try:
                node = c["ctrl"]
                for _ in range(25):
                    if node is None:
                        break
                    if node.GetRuntimeId() == hit_rid:
                        visible = True
                        break
                    node = node.GetParentControl()
            except Exception:
                visible = True
        if visible:
            kept.append(c)
    return kept


def dedupe_nearby(controls, threshold=10):
    """中心点距离小于 threshold 的控件只保留更靠上的（其余直接过滤）。"""
    # 先按中心 y 升序、再按 x 升序，保证更靠上的先被保留
    controls.sort(key=lambda c: ((c["rect"][1] + c["rect"][3]) // 2,
                                 (c["rect"][0] + c["rect"][2]) // 2))
    kept = []
    centers = []
    for c in controls:
        cx = (c["rect"][0] + c["rect"][2]) // 2
        cy = (c["rect"][1] + c["rect"][3]) // 2
        if any(((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5 <= threshold
               for ox, oy in centers):
            continue
        kept.append(c)
        centers.append((cx, cy))
    return kept


def draw_image(controls, base_img=None, out_path=None):
    if base_img is None:
        shot = pyautogui.screenshot().convert("RGBA")
    else:
        shot = base_img.convert("RGBA")
    overlay = Image.new("RGBA", shot.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("msyh.ttc", 11)
    except Exception:
        font = ImageFont.load_default()

    marks = []
    for i, c in enumerate(controls, 1):
        left, top, right, bottom = c["rect"]
        # 极浅的红色背景 + 微透明细红边框
        odraw.rectangle([left, top, right, bottom],
                        fill=(255, 0, 0, 15), outline=(255, 0, 0, 210), width=1)
        label = str(i)
        bbox = odraw.textbbox((0, 0), label, font=font)
        tgw, tgh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 2
        bw, bh = tgw + pad * 2, tgh + pad * 2
        # 序号标签放在框左上角内侧
        lx, ly = left, top
        # 半透明绿色背景
        odraw.rectangle([lx, ly, lx + bw, ly + bh], fill=(0, 255, 0, 150))
        # 按字形真实边界在框内居中，避免数字偏下
        tx = lx + (bw - tgw) // 2 - bbox[0]
        ty = ly + (bh - tgh) // 2 - bbox[1]
        marks.append((label, tx, ty, font))

    shot = Image.alpha_composite(shot, overlay).convert("RGB")
    draw = ImageDraw.Draw(shot)
    # 黑色序号
    for label, lx, ly, font in marks:
        draw.text((lx, ly), label, fill=(0, 0, 0), font=font)
    if out_path:
        shot.save(out_path)
    return shot


def main():
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")
    os.makedirs(out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    img_path = os.path.join(out_dir, f"controls_{ts}.png")

    print("正在枚举桌面控件 ...")
    controls = collect_controls()
    for c in controls:
        c["name"] = sanitize(c["name"])
        c["class"] = sanitize(c["class"])
        c["type"] = sanitize(c["type"])
    controls = filter_large(controls)
    controls = filter_oversized(controls, 450)
    controls = filter_occluded(controls)
    controls = dedupe_nearby(controls, threshold=20)
    print(f"共识别到 {len(controls)} 个控件\n")

    for i, c in enumerate(controls, 1):
        left, top, right, bottom = c["rect"]
        print(f"[{i:4d}] {c['type']:<12} {c['name'][:30]:<30} "
              f"cls={c['class'][:20]:<20} center=({ (left+right)//2 },{ (top+bottom)//2 })")

    path = draw_image(controls, out_path=img_path)
    print(f"\n图片已保存：{path}")


if __name__ == "__main__":
    main()
