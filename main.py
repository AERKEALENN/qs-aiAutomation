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
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import ui_inspect


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


def parse_instruction(cmd):
    for sep in ['并输入', '并键入']:
        if sep in cmd:
            parts = cmd.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return cmd.strip(), None


CLICK_PROMPT = lambda inst, step, legend, last_desc=None, tried=None: (
    f"你是桌面自动化助手，帮用户完成操作。\n"
    f"目标：\"{inst}\"（第 {step} 步）\n\n"
    + (f"刚做了：{last_desc}\n" if last_desc else "")
    + f"图片是当前屏幕截图，上面用红框+绿底编号标注了所有可交互控件。\n"
    f"编号 1~{len(legend)} 与下方说明一一对应：\n"
    + "\n".join(f"  [{i}] {c['type']} {c['name']}" for i, c in enumerate(legend, 1))
    + "\n\n"
    + (f"已排除的编号（不要重复选）：{', '.join(tried)}\n\n" if tried else "")
    + f"选择完成下一步所需的控件编号，返回 JSON：\n"
    f"  选控件：{{\"choice\": 12, \"action\": \"left\"}}\n"
    f"  任务完成：{{\"done\": true, \"summary\": \"已发送消息\"}}\n"
    f"  需要等待：{{\"action\": \"wait\", \"wait_sec\": {WAIT_MAX}}}\n"
    f"action 可选：\n"
    f"  left   = 左键点击\n"
    f"  right  = 右键点击\n"
    f"  paste  = 点击后粘贴（需 text，可选 button 指定 left/right）\n"
    f"  scroll = 滚动（需 lines，正=上/负=下）\n"
    f"  back   = 后退/重选其它编号\n"
)


def parse_click_response(text):
    """从模型回复提取点击决策 JSON（兼容代码块/闲杂文字）。"""
    return _json_extract(text)


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


def do_action(action, ox, oy, paste_text, paste_from_ai, scroll_lines, click_button):
    """在 (ox, oy) 执行动作。返回简短描述。"""
    pyautogui.moveTo(int(ox), int(oy), duration=0.3)
    desc = f"{action} ({int(ox)},{int(oy)})"
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
    if paste_from_ai:
        desc += f" 粘贴\"{paste_from_ai}\""
    elif paste_text:
        desc += f" 粘贴\"{paste_text}\""
    return desc


def mode_click(client, instruction):
    _, paste_text = parse_instruction(instruction)
    print(f"[\u76ee\u6807] {instruction}")
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

        # 枚举桌面控件并编号
        controls = ui_inspect.collect_controls()
        for c in controls:
            c["name"] = ui_inspect.sanitize(c["name"])
            c["class"] = ui_inspect.sanitize(c["class"])
            c["type"] = ui_inspect.sanitize(c["type"])
        controls = ui_inspect.filter_large(controls)
        controls = ui_inspect.filter_oversized(controls, 450)
        controls = ui_inspect.filter_occluded(controls)
        controls = ui_inspect.dedupe_nearby(controls, 20)
        print(f"[控件] 识别到 {len(controls)} 个可交互控件")

        if not controls:
            print("[控件] 未识别到可交互控件，跳过本步")
            step_lines.append("未识别到控件")
            for line in step_lines:
                log_write(line)
            time.sleep(3)
            continue

        tried = set()
        done_step = False
        wait_continue = False

        for locate_round in range(4):
            # 生成带编号的截图
            ctrl_img = ui_inspect.draw_image(controls, base_img=pil_full)
            b64 = encode_image(ctrl_img, label=f"控件#{step}", scale=0.70,
                               save_view=f"step{step}_controls.jpg", fmt='JPEG', qual=80)

            prompt = CLICK_PROMPT(instruction, step, controls, last_desc, sorted(tried))
            resp, reasoning_text, messages = call_vision_model(
                client, b64, prompt, label=f"选择#{step}",
                reasoning=_reasoning(1), history=messages)
            step_lines.append(f"AI回复: {resp}")
            if reasoning_text:
                step_lines.append(f"AI思考: {reasoning_text}")

            data = parse_click_response(resp)

            if data and data.get("done"):
                summary = data.get("summary", "")
                print(f"[完成] {summary}")
                step_lines.append(f"完成: {summary}")
                for line in step_lines:
                    log_write(line)
                done_step = True
                break

            if data and data.get("action") == "wait":
                wait_sec = min(WAIT_MAX, max(1, int(data.get("wait_sec", 3))))
                print(f"[等待] {wait_sec}秒")
                step_lines.append(f"等待{wait_sec}秒")
                for line in step_lines:
                    log_write(line)
                time.sleep(wait_sec)
                wait_continue = True
                break

            choice = data.get("choice") if data else None
            if isinstance(choice, str):
                try:
                    choice = int(choice)
                except ValueError:
                    choice = None
            if not isinstance(choice, int) or not (1 <= choice <= len(controls)):
                if locate_round < 3:
                    print("AI 解析失败，重试...")
                    tried.add(str(choice))
                    continue
                else:
                    print("错误：AI 解析失败")
                    step_lines.append("AI 解析失败")
                    for line in step_lines:
                        log_write(line)
                    done_step = True
                    break

            c = controls[choice - 1]
            left, top, right, bottom = c["rect"]
            ox, oy = (left + right) // 2, (top + bottom) // 2
            action = (data.get("action") or "left").strip().lower()
            paste_from_ai = data.get("text", "") or ""
            scroll_lines = data.get("lines", 0)
            if isinstance(scroll_lines, (int, float)):
                scroll_lines = int(scroll_lines)
            else:
                scroll_lines = 0
            button = (data.get("button") or "left").strip().lower()

            step_lines.append(
                f"选择 #{choice} {c['type']} {c['name']} -> {action}"
                + (f" text={paste_from_ai}" if paste_from_ai else "")
                + (f" lines={scroll_lines}" if scroll_lines else ""))

            if action == 'back':
                tried.add(str(choice))
                step_lines.append(f"后退: #{choice}")
                continue

            desc = do_action(action, ox, oy, paste_text, paste_from_ai, scroll_lines, button)
            last_click = (ox, oy)
            last_desc = desc
            step_lines.append(f"坐标: ({int(ox)},{int(oy)}) {desc}")
            break

        if done_step:
            if wait_continue:
                continue
            break

        step_lines.append("等待3秒")
        for line in step_lines:
            log_write(line)
        time.sleep(3)
    else:
        print(f"已达到最大步数 {MAX_STEPS}，停止")
        log_write(f"达到最大步数 {MAX_STEPS}")

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
