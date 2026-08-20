# 部署说明（离线/保密版）

## 1. 原则

- 只连接公司 IMAP 邮箱服务器。
- 只调用本机 `Ollama`，默认仅允许 `localhost / 127.0.0.1 / ::1`。
- 不接入任何第三方 SaaS，不需要在互联网上注册账号。
- 所有结果仅写入本地 SQLite / Markdown / JSONL / CSV。

## 2. 安装

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> 注意：新版现代界面需要 `PySide6`。如果公司电脑不能联网安装，请先在允许的环境下载 wheel，再按公司流程离线安装。

## 3. 配置

复制 `.env.example` 为 `.env`，或直接在 GUI 的“设置”页填写并点保存。`.env` 已被 `.gitignore` 忽略，不要提交。

## 4. 启动现代界面

直接双击项目目录里的：

```text
启动邮件监控.bat
```

也可以命令行启动：

```powershell
python mail_monitor_gui.py
python app.py gui
```

启动逻辑：

- 优先打开 PySide6 现代工作台。
- 如果缺少 PySide6，不会闪退，会提示：`pip install PySide6`。
- 缺少 PySide6 时可选择打开旧版 Tkinter 备用界面。

旧版备用界面也可以直接运行：

```powershell
python mail_monitor_tk.py
```

## 5. 现代界面结构

- 仪表盘：今日处理数、高优先邮件数、本地记录数、Ollama 状态、快速操作。
- 收件工作台：紧急度/分类/关键词筛选，邮件列表，右侧详情卡片。
- 规则与分类：分类、白名单、关键词、AI 输入长度、重试次数。
- 设置：公司 IMAP、本地 Ollama、本地存储和保密提示。
- 日志与导出：运行日志，CSV / Markdown / JSONL 导出。

## 6. 保密设计

- 邮件正文只会进入本机 Ollama：`http://localhost:11434`。
- 默认拒绝远程 Ollama 地址；除非显式设置 `ALLOW_REMOTE_OLLAMA=1`。
- 数据库 `mail_monitor.db`、日志、导出文件、`.env` 都只在本地。
- 不需要 GitHub、OpenAI、Google、Microsoft Graph 或任何第三方账号注册。

## 7. 当前技术说明

Python 标准库支持 IMAP IDLE 推送（`PREFER_IDLE=1`，默认）以降低空闲占用；IDLE 不可用时会自动回退到“UID 增量轻量轮询”。要满足 10 秒验收，保持：

```env
POLL_INTERVAL=10
PREFER_IDLE=1
```

## 8. P0 可靠性优化说明

新版已加入以下保护：

- 启动诊断：启动失败或缺少 PySide6 时，会写入 `startup_error.log` / `launcher_error.log`，包含 Python 路径、版本、工作目录和依赖状态。
- 状态机：界面状态分为 `idle / watching / collecting / stopping / error`，运行中会自动禁用重复启动按钮。
- 人话错误：常见 Ollama、IMAP、日期和配置错误会显示可操作提示，技术详情保留在日志页。
- 首次启动向导：首次未配置邮箱时，自动引导填写 IMAP、测试 IMAP、测试 Ollama、保存并开始监控。
- 配置校验：保存前会检查 IMAP 服务器、端口、账号、Ollama 地址和日期范围。
