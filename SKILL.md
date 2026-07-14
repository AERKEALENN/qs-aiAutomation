# SKILL.md

基于视觉大模型的桌面自动化工具，用自然语言指令完成多步骤桌面操作。

## 用法

```bash
python main.py "发微信给哥哥说你好"
```

常用指令：

```bash
python main.py "<自然语言任务>"     # 连续自动操作
python main.py --analyze "<问题>"   # 仅截图并分析界面
python main.py --screenshot         # 仅截图
```

## 工作流程

1. 全屏截图，并用 UI Automation 枚举可见控件，叠加红色框与绿色编号（Set-of-Marks）
2. AI 根据编号选择目标控件并决定动作（点击 / 粘贴 / 滚动等）
3. 执行动作，循环直到任务完成

## 配置

复制 `.env.example` 为 `.env` 并填入：

- `API_BASE` / `MODEL` / `API_KEY` — 模型接入
- `API_REASONING_1` — 控件选择步思考开关（`disabled` 关，`high`/`medium`/`low`/`enabled` 开）
- `API_REASONING_2` — 预留（当前未使用，必填可填 `disabled`）
- `API_REASONING_ANALYZE` — 分析步思考开关
- `API_WAIT_MAX` — AI 可控最大等待秒数
- `MAX_STEPS` — 最大执行步数

## 输出

- `photos/run_时间戳/` — 每步截图与 AI 视图
- `logs/log_时间戳.txt` — 详细运行日志

## 示例

```bash
# 发消息
python main.py "打开微信，给文件传输助手发送你好"

# 带内容粘贴
python main.py "在浏览器里打开百度并输入 Python 教程 并搜索"

# 多步骤任务
python main.py "打开记事本，输入 hello world，保存到桌面"

# 分析当前界面
python main.py --analyze "这个窗口有哪些可以点击的按钮？"

# 仅截图
python main.py --screenshot
```
