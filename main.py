#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QSai 桌面自动化 - 命令行截图分析与点击工具
"""

import os
import sys
import io
import base64
import json
import re
import time
import platform
from datetime import datetime

import pyautogui
import pyperclip
import cv2
import numpy as np
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

API_BASE = os.getenv('API_BASE')
MODEL = os.getenv('MODEL')
API_KEY = os.getenv('API_KEY')
API_TIMEOUT = os.getenv('API_TIMEOUT')
API_REASONING_1 = os.getenv('API_REASONING_1')
API_REASONING_2 = os.getenv('API_REASONING_2')
API_REASONING_ANALYZE = os.getenv('API_REASONING_ANALYZE')
API_WAIT_MAX = os.getenv('API_WAIT_MAX')
MAX_STEPS = os.getenv('MAX_STEPS')

required_vars = {
    'API_BASE': API_BASE,
    'MODEL': MODEL,
    'API_KEY': API_KEY,
    'API_TIMEOUT': API_TIMEOUT,
    'API_REASONING_1': API_REASONING_1,
    'API_REASONING_2': API_REASONING_2,
    'API_REASONING_ANALYZE': API_REASONING_ANALYZE,
    'API_WAIT_MAX': API_WAIT_MAX,
    'MAX_STEPS': MAX_STEPS,
}
missing = [k for k, v in required_vars.items() if not v]
if missing:
    print(f"错误：请在 .env 文件中设置以下变量：{', '.join(missing)}")
    sys.exit(1)

API_TIMEOUT = int(API_TIMEOUT)
WAIT_MAX = int(API_WAIT_MAX)
MAX_STEPS = int(MAX_STEPS)

PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'photos')
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

RUN_DIR = None


def take_screenshot(save_scale=0.70, save_file=True):
    raw = pyautogui.screenshot()
    if save_file:
        save_dir = RUN_DIR or PHOTOS_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.jpg"
        filepath = os.path.join(save_dir, filename)
        w, h = raw.size
        thumb = raw.resize((int(w * save_scale), int(h * save_scale)), Image.LANCZOS)
        thumb.save(filepath, quality=68)
    else:
        filepath = ''
    return raw, filepath


def encode_image(pil_img, scale=0.70, label="", save_view=None, fmt='PNG', qual=95):
    save_dir = RUN_DIR or PHOTOS_DIR
    w, h = pil_img.size
    new_w, new_h = int(w * scale), int(h * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
    if save_view:
        view_path = os.path.join(save_dir, save_view)
        pil_img.save(view_path, quality=qual)
    buf = io.BytesIO()
    pil_img.save(buf, format=fmt, quality=qual)
    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return b64


def pil_to_cv2(pil_img):
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_img):
    return Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))


def draw_grid_full(img_cv, grid=6):
    h, w = img_cv.shape[:2]
    cw = w // grid
    ch = h // grid
    for i in range(1, grid):
        cv2.line(img_cv, (i * cw, 0), (i * cw, h), (0, 255, 0), 2)
        cv2.line(img_cv, (0, i * ch), (w, i * ch), (0, 255, 0), 2)
    rows = [chr(ord('A') + i) for i in range(grid)]
    for r in range(grid):
        for c in range(grid):
            label = f"{rows[r]}{c + 1}"
            cx = c * cw + cw // 2
            cy = r * ch + ch // 2
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.putText(img_cv, label, (cx - tw // 2, cy + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return img_cv


L2_GRID = 8

def draw_grid_in_rect(img_cv, rect, grid=L2_GRID):
    l, t, r, b = [int(v) for v in rect]
    cv2.rectangle(img_cv, (l, t), (r, b), (0, 255, 0), 2)
    cw = (r - l) / grid
    ch = (b - t) / grid
    for i in range(1, grid):
        x = int(l + i * cw)
        cv2.line(img_cv, (x, t), (x, b), (0, 255, 0), 1)
        y = int(t + i * ch)
        cv2.line(img_cv, (l, y), (r, y), (0, 255, 0), 1)
    for row in range(grid):
        for col in range(grid):
            label = f"{chr(65 + col)}{row + 1}"
            cx = int(l + (col + 0.5) * cw)
            cy = int(t + (row + 0.5) * ch)
            cv2.putText(img_cv, label, (cx - 8, cy + 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)
    return img_cv


def get_grid_cell_center(choice, rect, grid=L2_GRID):
    l, t, r, b = rect
    cw = (r - l) / grid
    ch = (b - t) / grid
    choice = choice.strip().upper()
    if len(choice) < 2 or not choice[0].isalpha() or not choice[1:].isdigit():
        return None
    col = ord(choice[0]) - ord('A')
    row = int(choice[1:]) - 1
    if col < 0 or col >= grid or row < 0 or row >= grid:
        return None
    cx = l + (col + 0.5) * cw
    cy = t + (row + 0.5) * ch
    return (cx, cy)


def expand_rect(rect, img_w, img_h, ratio=0.1):
    l, t, r, b = rect
    dw = (r - l) * ratio
    dh = (b - t) * ratio
    return (
        max(0, l - dw),
        max(0, t - dh),
        min(img_w, r + dw),
        min(img_h, b + dh),
    )


API_TIMEOUT = int(os.getenv('API_TIMEOUT', '120'))

def _reasoning(suffix):
    m = {'1': API_REASONING_1, '2': API_REASONING_2, 'ANALYZE': API_REASONING_ANALYZE}
    v = m.get(str(suffix), '')
    return v if v else False

def call_vision_model(client, b64_img, prompt, label="", reasoning="", history=None):
    print(f"[API] {label} 请求模型 {MODEL} (超时 {API_TIMEOUT}s) ...")
    t0 = time.time()
    user_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
        ]
    }
    messages = (history or []) + [user_msg]
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "timeout": API_TIMEOUT,
    }
    if reasoning == 'disabled':
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    elif reasoning:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        kwargs["temperature"] = 0.1
    resp = client.chat.completions.create(**kwargs)
    cost = time.time() - t0
    msg = resp.choices[0].message
    text = msg.content.strip()
    reasoning_text = None
    if reasoning and reasoning != 'disabled':
        reasoning_text = getattr(msg, 'reasoning_content', None) or getattr(msg, 'reasoning', None)
    print(f"[API] {label} 响应耗时 {cost:.1f}s")
    asst_msg = {"role": "assistant", "content": text}
    if reasoning_text:
        asst_msg["reasoning_content"] = reasoning_text
    return text, reasoning_text, messages + [asst_msg]


def _json_extract(text):
    """从模型回复中提取第一个 JSON 对象（兼容 markdown 代码块、闲杂文字）。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r'(\{.*?"choice".*?\})', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def parse_level2_response(text):
    data = _json_extract(text)
    if not data:
        return None, None, None, None, 'left'
    choice = data.get("choice", "").strip()
    action = data.get("action", "left").strip()
    paste_text_data = data.get("text", "")
    scroll_lines = data.get("lines", 0)
    button = data.get("button", "left").strip().lower()
    if isinstance(scroll_lines, (int, float)):
        scroll_lines = int(scroll_lines)
    else:
        scroll_lines = 0
    return choice, action, paste_text_data, scroll_lines, button


def parse_instruction(cmd):
    for sep in ['并输入', '并键入']:
        if sep in cmd:
            parts = cmd.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return cmd.strip(), None


LEVEL1_PROMPT = lambda inst, tried_cells=None: (
    f"你是桌面自动化助手，帮用户完成操作。\n"
    f"目标：\"{inst}\"\n\n"
    f"图片是当前屏幕截图，叠加了 9×9 网格。\n"
    f"编号规则：行 A~I（上->下），列 1~9（左->右）\n"
    f"  A1=左上  A2=上中  ...  A9=右上  "
    f"B1=左中  ...  I9=右下\n"
    f"示例：E5=屏幕正中央，A1=左上角，I9=右下角\n\n"
    + (f"已排除的格子（不要重复选）：{', '.join(tried_cells)}\n\n" if tried_cells else "")
    + f"找到下一步需要操作的元素所在格子，返回 JSON：\n"
    f"  选格子：{{\"choice\": \"C3\"}}\n"
    f"  任务完成：{{\"done\": true, \"summary\": \"已发送消息\"}}\n"
    f"  需要等待：{{\"action\": \"wait\", \"wait_sec\": {WAIT_MAX}}} (1~{WAIT_MAX}秒)"
)

LATER_L1_PROMPT = lambda inst, step, last_desc=None, tried_cells=None: (
    f"接上一步，继续目标：\"{inst}\"（第 {step} 步）\n"
    + (f"刚做了：{last_desc}\n" if last_desc else "")
    + f"网格 9×9，行 A~I 列 1~9，规则同上。\n"
    + (f"已排除：{', '.join(tried_cells)}\n" if tried_cells else "")
    + f"返回 {{\"choice\":\"格子\"}}，或 {{\"done\":true,\"summary\":\"...\"}}，"
    f"或 {{\"action\":\"wait\",\"wait_sec\":{WAIT_MAX}}}"
)
LEVEL2_PROMPT = lambda inst, cell, tried_cells=None: (
    f"这是 {cell} 格的放大区域，8×8 网格规则同前。\n"
    + (f"已排除：{', '.join(tried_cells)}\n" if tried_cells else "")
    + f"动作：left/right/paste(text+可选button)/scroll(lines)/back\n"
    f"返回 {{\"choice\":\"格子\",\"action\":\"left\"}} 等"
)


# ── 模式 ──────────────────────────────────────────────

def mode_screenshot():
    pil_img, path = take_screenshot()
    print(path)
    return pil_img, path


DEFAULT_ANALYZE_PROMPT = (
    "请详细分析这张屏幕截图。\n\n"
    "1. 描述整体界面布局（顶部栏、侧边栏、主内容区、底部等）。\n"
    "2. 逐一列出所有可见的可交互组件，包括但不限于：\n"
    "   - 按钮\n"
    "   - 输入框 / 搜索栏\n"
    "   - 图标\n"
    "   - 菜单项\n"
    "   - 链接 / 标签页\n"
    "   - 下拉框 / 选择器\n"
    "   - 复选框 / 单选按钮\n"
    "   - 开关 / 切换\n"
    "3. 对每个组件说明其在屏幕上的大致位置（如「左上角」、「中央偏右」、「底部导航栏左侧」、「标题下方居中」等）。\n\n"
    "格式不限，简洁清晰即可。"
)

def mode_analyze(client, custom_question=None):
    pil_img, path = take_screenshot()
    b64 = encode_image(pil_img, label="分析图", save_view="ai_view_analyze.jpg")
    prompt = custom_question if custom_question else DEFAULT_ANALYZE_PROMPT
    description, _, _ = call_vision_model(client, b64, prompt, label="分析", reasoning=_reasoning('ANALYZE'))
    print(f"截图路径：{path}")
    print(f"模型描述：{description}")


def parse_major_choice(text):
    data = _json_extract(text)
    if not data:
        return None
    for key in ('choice', 'cell', 'grid', 'target', 'sub'):
        val = data.get(key)
        if val:
            return str(val).strip()
    return None


def mode_click(client, instruction):
    _, paste_text = parse_instruction(instruction)
    print(f"[\u76ee\u6807] {instruction}")
    L1_GRID = 9
    messages = None
    last_click = None
    last_desc = None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(LOG_DIR, f"log_{timestamp}.txt")
    log_fh = open(log_path, 'w', encoding='utf-8')
    def log_write(text):
        log_fh.write(text + '\n')
        log_fh.flush()
    log_write(f"目标: {instruction}")
    log_write(f"时间: {timestamp}")

    global RUN_DIR
    RUN_DIR = os.path.join(PHOTOS_DIR, f"run_{timestamp}")
    os.makedirs(RUN_DIR, exist_ok=True)

    for step in range(1, MAX_STEPS + 1):
        step_lines = []
        print(f"\n--- 第 {step} 步 ---")
        step_lines.append(f"=== 第 {step} 步 ===")

        pil_full, _ = take_screenshot(save_file=False)
        W, H = pil_full.size
        cv_full = pil_to_cv2(pil_full)

        tried_cells = set()
        done_step = False
        wait_continue = False

        for locate_round in range(4):
            cv_grid = draw_grid_full(cv_full.copy(), grid=L1_GRID)

            if last_click:
                lx, ly = last_click
                cv2.circle(cv_grid, (int(lx), int(ly)), 8, (0, 165, 255), 2)
                cv2.line(cv_grid, (int(lx)-10, int(ly)), (int(lx)+10, int(ly)), (0, 165, 255), 1)
                cv2.line(cv_grid, (int(lx), int(ly)-10), (int(lx), int(ly)+10), (0, 165, 255), 1)

            b64 = encode_image(cv2_to_pil(cv_grid), label=f"L1#{step}", scale=0.80, save_view=f"step{step}_L1.jpg", fmt='JPEG', qual=80)

            if step == 1:
                prompt = LEVEL1_PROMPT(instruction, tried_cells) if tried_cells else LEVEL1_PROMPT(instruction)
            else:
                prompt = LATER_L1_PROMPT(instruction, step, last_desc, tried_cells) if tried_cells else LATER_L1_PROMPT(instruction, step, last_desc)

            resp, reasoning_text, messages = call_vision_model(client, b64, prompt, label=f"L1#{step}", reasoning=_reasoning(1), history=messages)
            step_lines.append(f"L1回复: {resp}")
            if reasoning_text:
                step_lines.append(f"L1思考: {reasoning_text}")

            data = _json_extract(resp)

            if data and data.get("done"):
                summary = data.get("summary", "")
                print(f"[\u5b8c\u6210] {summary}")
                step_lines.append(f"\u5b8c\u6210: {summary}")
                for line in step_lines: log_write(line)
                done_step = True
                break

            if data and data.get("action") == "wait":
                wait_sec = min(WAIT_MAX, max(1, int(data.get("wait_sec", 3))))
                print(f"[\u7b49\u5f85] {wait_sec}\u79d2")
                step_lines.append(f"\u7b49\u5f85{wait_sec}\u79d2")
                for line in step_lines: log_write(line)
                time.sleep(wait_sec)
                wait_continue = True
                break

            cell = parse_major_choice(resp)
            upper = cell.upper() if cell else ''
            if upper and re.match(r'^[A-I][1-9]$', upper):
                row = ord(upper[0]) - ord('A')
                col = int(upper[1]) - 1
            else:
                if locate_round < 3:
                    print("L1\u89e3\u6790\u5931\u8d25\uff0c\u91cd\u8bd5...")
                    tried_cells.add(upper or '?')
                    continue
                else:
                    print("\u9519\u8bef\uff1aL1\u89e3\u6790\u5931\u8d25")
                    step_lines.append("L1\u89e3\u6790\u5931\u8d25")
                    for line in step_lines: log_write(line)
                    done_step = True
                    break

            cell_label = f"{chr(65+row)}{col+1}"
            step_lines.append(f"L1: {cell_label}")

            cell_w = W / L1_GRID
            cell_h = H / L1_GRID
            lu = col * cell_w
            tu = row * cell_h
            ru = (col + 1) * cell_w
            bu = (row + 1) * cell_h
            l1, t1, r1, b1 = expand_rect((lu, tu, ru, bu), W, H, 0.4)
            crop = cv_full[int(t1):int(b1), int(l1):int(r1)]
            orig_rect = (int(lu - l1), int(tu - t1), int(ru - l1), int(bu - t1))

            cv_grid2 = draw_grid_in_rect(crop.copy(), orig_rect)
            b64_2 = encode_image(cv2_to_pil(cv_grid2), label=f"L2#{step}", scale=1.0, save_view=f"step{step}_L2.jpg", fmt='JPEG', qual=80)

            l2_prompt = LEVEL2_PROMPT(instruction, cell_label, tried_cells) if tried_cells else LEVEL2_PROMPT(instruction, cell_label)
            resp2, reasoning_text2, messages = call_vision_model(client, b64_2, l2_prompt, label=f"L2#{step}", reasoning=_reasoning(2), history=messages)
            step_lines.append(f"L2回复: {resp2}")
            if reasoning_text2:
                step_lines.append(f"L2思考: {reasoning_text2}")

            data2 = _json_extract(resp2)
            if data2 and data2.get("done"):
                summary = data2.get("summary", "")
                print(f"[\u5b8c\u6210] {summary}")
                step_lines.append(f"\u5b8c\u6210: {summary}")
                for line in step_lines: log_write(line)
                done_step = True
                break

            choice, action, paste_from_ai, scroll_lines, click_button = parse_level2_response(resp2)
            if not choice:
                if locate_round < 3:
                    print("L2\u89e3\u6790\u5931\u8d25\uff0c\u91cd\u8bd5...")
                    continue
                else:
                    print("\u9519\u8bef\uff1aL2\u89e3\u6790\u5931\u8d25")
                    step_lines.append("L2\u89e3\u6790\u5931\u8d25")
                    for line in step_lines: log_write(line)
                    done_step = True
                    break

            step_lines.append(f"L2: {choice} {action}" +
                  (f" text={paste_from_ai}" if paste_from_ai else "") +
                  (f" lines={scroll_lines}" if scroll_lines else ""))

            if action == 'back':
                tried_cells.add(cell_label)
                step_lines.append(f"\u540e\u9000: {cell_label}")
                continue

            pt = get_grid_cell_center(choice, orig_rect)
            if not pt:
                print(f"\u9519\u8bef\uff1a\u65e0\u6548\u683c\u5b50 {choice}")
                step_lines.append(f"\u65e0\u6548\u683c\u5b50: {choice}")
                for line in step_lines: log_write(line)
                done_step = True
                break

            cx, cy = pt
            ox = l1 + cx
            oy = t1 + cy
            step_lines.append(f"\u5750\u6807: ({int(ox)},{int(oy)}) {action}")

            pyautogui.moveTo(int(ox), int(oy), duration=0.3)

            if action == 'scroll':
                pyautogui.scroll(scroll_lines)
            elif action == 'right':
                pyautogui.click(button='right')
            elif action == 'paste':
                paste_content = paste_from_ai or paste_text
                btn = click_button if click_button in ('left', 'right') else 'left'
                if paste_content:
                    pyautogui.click(button=btn)
                    time.sleep(1.0)
                    pyperclip.copy(paste_content)
                    time.sleep(0.2)
                    mod = 'command' if platform.system() == 'Darwin' else 'ctrl'
                    pyautogui.hotkey(mod, 'v')
                else:
                    pyautogui.click(button=btn)
            else:
                pyautogui.click()
                if paste_text:
                    time.sleep(0.2)
                    pyperclip.copy(paste_text)
                    time.sleep(0.2)
                    mod = 'command' if platform.system() == 'Darwin' else 'ctrl'
                    pyautogui.hotkey(mod, 'v')

            last_click = (ox, oy)
            last_desc = f"{action} ({int(ox)},{int(oy)})"
            if paste_from_ai:
                last_desc += f" \u7c98\u8d34\"{paste_from_ai}\""
            elif paste_text:
                last_desc += f" \u7c98\u8d34\"{paste_text}\""
            break

        if done_step:
            if wait_continue:
                continue
            break

        step_lines.append("\u7b49\u5f853\u79d2")
        for line in step_lines: log_write(line)
        time.sleep(3)
    else:
        print(f"\u5df2\u8fbe\u6700\u5927\u6b65\u6570 {MAX_STEPS}\uff0c\u505c\u6b62")
        log_write(f"\u8fbe\u5230\u6700\u5927\u6b65\u6570 {MAX_STEPS}")

    log_fh.close()
    print(f"\n[日志] {log_path}")
    print(f"[图片] {RUN_DIR}")


# ── 入口 ──────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("用法：")
        print("  python main.py --screenshot                 全屏截图")
        print("  python main.py --analyze [问句]             截图并分析界面")
        print('  python main.py "<指令>"                    连续自动操作（如 "发微信给哥哥说你好"）')
        sys.exit(1)

    client = OpenAI(api_key=API_KEY, base_url=API_BASE)
    arg = sys.argv[1]

    if arg == '--screenshot':
        mode_screenshot()
    elif arg == '--analyze':
        question = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else None
        mode_analyze(client, question)
    else:
        mode_click(client, arg)


if __name__ == '__main__':
    main()
