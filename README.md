# QSai 桌面自动化

基于视觉大模型的桌面自动化工具。自动截图、识别界面、模拟点击，完成多步骤桌面操作。

## 工作原理

1. 截取全屏 → 叠加 9×9 网格 → AI 选择目标区域
2. 放大选中区域 → 叠加 8×8 网格 → AI 精确定位并决定动作
3. 执行动作（点击 / 粘贴 / 滚动）→ 循环直到任务完成

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
| `API_REASONING_1` | L1 思考模式（`high`/`medium`/`low`/`enabled`/`disabled`） |
| `API_REASONING_2` | L2 思考模式 |
| `API_REASONING_ANALYZE` | 分析模式思考模式 |
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

- `photos/run_时间戳/` — 每步截图和 AI 视图
- `logs/log_时间戳.txt` — 详细运行日志

## 许可证

MIT
