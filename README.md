# QSai 桌面自动化

基于视觉大模型的桌面自动化工具。自动截图、识别界面、模拟点击，完成多步骤桌面操作。

## 工作原理

1. 截取全屏 → 用 UI Automation 枚举可见控件 → 在截图上叠加红色框 + 绿色编号（Set-of-Marks）
2. AI 直接根据编号选择目标控件并决定动作（左键 / 右键 / 粘贴 / 滚动等）
3. 执行动作 → 循环直到任务完成

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制环境变量模板并填写：

```bash
cp .env.example .env
```

编辑 `.env`，所有变量均为必填：

| 变量 | 说明 |
|------|------|
| `API_BASE` | API 地址 |
| `MODEL` | 模型名 |
| `API_KEY` | API 密钥 |
| `API_TIMEOUT` | 请求超时（秒） |
| `API_REASONING_1` | 控件选择步思考模式（`high`/`medium`/`low`/`enabled`/`disabled`） |
| `API_REASONING_2` | 预留（L2 思考模式，当前未使用，必填可填 `disabled`） |
| `API_REASONING_ANALYZE` | 分析步思考模式 |
| `API_WAIT_MAX` | AI 控制等待的最大秒数 |
| `MAX_STEPS` | 最大执行步数 |

### 3. 使用

```bash
# 连续自动化操作
python main.py "发微信给哥哥说你好"

# 截图分析界面
python main.py --analyze "这个界面有什么功能？"

# 纯截图
python main.py --screenshot
```

## 输出

- `photos/run_时间戳/` — 每步控件编号截图（`stepN_controls.jpg`）与 AI 视图
- `logs/log_时间戳.txt` — 详细运行日志

## 许可证

MIT
