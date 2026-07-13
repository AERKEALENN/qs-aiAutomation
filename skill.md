# QSai 桌面自动化 使用技能

本文件说明如何驱动 QSai 桌面自动化完成桌面任务。

## 适用场景

- 通过自然语言指令自动操作桌面应用（发消息、填表、点击按钮等）
- 需要多步骤、依赖视觉定位的界面交互

## 调用方式

```bash
python main.py "<自然语言指令>"
```

示例：

```bash
python main.py "发微信给哥哥说你好"
python main.py "打开浏览器搜索 Python 教程"
python main.py "在记事本里输入 hello world 并保存"
```

## AI 可执行的操作

### L1 层级（全屏 9×9 网格）

AI 选择目标区域，返回 JSON：

```json
{"choice": "E5"}
```

控制指令：

```json
{"done": true, "summary": "已完成"}
{"action": "wait", "wait_sec": 5}
```

### L2 层级（放大区域 8×8 网格）

AI 精确定位并执行动作：

| 动作 | JSON | 行为 |
|------|------|------|
| left | `{"choice":"C3","action":"left"}` | 左键点击 |
| right | `{"choice":"C3","action":"right"}` | 右键点击 |
| paste | `{"choice":"C3","action":"paste","text":"你好","button":"left"}` | 点击 + 粘贴 |
| scroll | `{"choice":"D5","action":"scroll","lines":3}` | 滚动（正下负上） |
| back | `{"choice":"任意","action":"back"}` | 退回 L1 重选 |

## 提示词体系

- `LEVEL1_PROMPT` — 第一步完整说明网格与格式
- `LATER_L1_PROMPT` — 后续步骤，语气承接上文，只带变化信息
- `LEVEL2_PROMPT` — 二级定位与动作选择

上下文（messages 历史，含思考）逐轮累积传给模型。

## 环境变量

详见 `.env.example`，全部必填：

`API_BASE` / `MODEL` / `API_KEY` / `API_TIMEOUT` / `API_REASONING_1` / `API_REASONING_2` / `API_REASONING_ANALYZE` / `API_WAIT_MAX` / `MAX_STEPS`

思考控制：`disabled` 关闭，`high`/`medium`/`low`/`enabled` 开启。

## 输出

- `photos/run_时间戳/` — 每步截图与 AI 视图
- `logs/log_时间戳.txt` — 实时详细日志
