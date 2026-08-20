# mailkanshi · 公司邮件智能监控工具

**本地 · 离线 · 保密** 的公司邮件监控助手。它通过 IMAP 拉取公司邮箱新邮件，调用**本机 Ollama** 大模型做分类 / 摘要 / 紧急度判断 / 行动项抽取，结果只写入本地 SQLite 与导出文件，全程不接入任何第三方云服务。

> 主要使用场景：日本客户往来邮件（日文为主、中英文混合），需要快速识别报价、客户咨询、会议、加急等邮件并本地留档。

---

## ✨ 功能特性

- **实时监控**：支持 IMAP IDLE 推送，失败自动回退到 UID 增量轮询。
- **本地 AI 分析**：邮件正文只送到本机 Ollama（默认 `http://localhost:11434`），做分类、一句话摘要、紧急度（high / normal / low）、行动项抽取。
- **规则引擎**：发件人白名单、关键词命中可强制标记为高优先。
- **多语言**：面向中日双语场景优化的提示词。
- **附件识别**：解析附件文件名 / 类型 / 大小（不外传附件内容）。
- **智能去重**：Message-ID 去重 + 相同内容哈希缓存，避免对同一内容重复调用 LLM。
- **桌面通知**：高优先邮件弹出本地提醒。
- **现代界面**：PySide6 工作台（仪表盘 / 收件工作台 / 规则 / 设置 / 日志导出），缺少 PySide6 时可回退旧版 Tkinter 界面。
- **多种导出**：CSV / Markdown / JSONL。
- **命令行**：`watch` / `collect` / `models` / `export` 等子命令。

---

## 🔒 保密设计

- 邮件正文只进入本机 Ollama，默认**拒绝远程地址**（仅允许 `localhost / 127.0.0.1 / ::1`）。
- 本地 Ollama 请求自动**绕过公司代理**，避免被代理拦截。
- 不需要 GitHub / OpenAI / Google / Microsoft 等任何第三方账号。
- `.env`、数据库、日志、导出文件均保留在本地，且已被 `.gitignore` 忽略。

---

## 🚀 快速开始

### 1. 前置条件

- Python 3.10+
- 本机已安装并运行 [Ollama](https://ollama.com/)，并已拉取模型，例如：

  ```powershell
  ollama pull qwen2.5:3b
  ```

### 2. 安装依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> 现代界面需要 `PySide6`。若公司电脑不能联网安装，请在允许的环境下载 wheel 后按公司流程离线安装。

### 3. 配置

复制 `.env.example` 为 `.env` 并填写，或直接在 GUI「设置」页填写后保存（`.env` 不会被提交）。

### 4. 启动

Windows 直接双击：

```text
启动邮件监控.bat
```

或命令行：

```powershell
python mail_monitor_gui.py      # 现代界面（推荐）
python app.py gui               # 同上
python mail_monitor_tk.py       # 旧版 Tkinter 备用界面
```

---

## 🖥️ 界面结构

| 页面 | 说明 |
| --- | --- |
| 仪表盘 | 今日处理数、高优先邮件数、本地记录数、Ollama 状态、快速操作 |
| 收件工作台 | 按紧急度 / 分类 / 关键词筛选，邮件列表 + 详情卡片 |
| 规则与分类 | 分类列表、发件人白名单、高优先关键词、AI 输入长度、重试次数 |
| 设置 | 公司 IMAP、本地 Ollama（模型下拉可刷新）、存储与保密 |
| 日志与导出 | 运行日志，CSV / Markdown / JSONL 导出 |

---

## ⌨️ 命令行用法

```powershell
python app.py watch                                         # 启动常驻监控
python app.py collect --start 2026-08-01 --end 2026-08-20   # 按日期批量收集
python app.py models                                        # 列出本地 Ollama 模型
python app.py export --format csv --output out.csv          # 导出结果
```

---

## ⚙️ 主要配置项（`.env`）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `IMAP_SERVER` / `IMAP_PORT` | 公司邮箱服务器与端口 | — / `993` |
| `IMAP_USERNAME` / `IMAP_PASSWORD` | 账号与密码/授权码 | — |
| `IMAP_SSL` | 是否使用 SSL | `1` |
| `IMAP_FOLDER` | 监控的文件夹 | `INBOX` |
| `POLL_INTERVAL` | 轮询间隔秒（IDLE 不可用时生效） | `30` |
| `PREFER_IDLE` | 优先使用 IMAP IDLE 推送 | `1` |
| `OLLAMA_BASE_URL` | 本机 Ollama 地址 | `http://localhost:11434` |
| `OLLAMA_MODEL` | 使用的模型 | `qwen2.5:1.5b` |
| `ALLOW_REMOTE_OLLAMA` | 是否允许远程 Ollama（不推荐） | `0` |
| `CATEGORIES` | 分类标签（逗号分隔） | 报价,客户咨询,… |
| `RULE_WHITELIST` | 高优先发件人白名单 | 空 |
| `RULE_KEYWORDS` | 高优先关键词 | 紧急,urgent,… |
| `DESKTOP_NOTIFY` | 高优先邮件桌面通知 | `1` |
| `AI_CACHE_ENABLED` | 相同内容复用 AI 结果 | `1` |

完整清单见 [`.env.example`](.env.example)。

---

## 🗂️ 项目结构

```
app.py               命令行入口
mail_monitor_gui.py  现代界面入口（含 Tkinter 回退）
launcher.py          Windows 启动器
config.py            配置加载与校验
imap_watcher.py      IMAP 连接 / IDLE / 轮询
mail_parser.py       邮件解析（正文 / 附件 / 发件人）
ollama_client.py     本机 Ollama 客户端
rules.py             规则引擎
service.py           监控主流程与任务队列
storage.py           SQLite 存储与去重缓存
exporter.py          CSV / Markdown / JSONL 导出
qt_gui.py            PySide6 界面
qt_worker.py         界面后台线程
qt_theme.py          界面样式
gui.py               旧版 Tkinter 界面
tests/               单元测试
```

---

## 🧪 开发

```powershell
python -m pytest -q                 # 运行测试
python -m ruff check .              # 代码检查
python build_exe.py                 # 打包 exe（需 PyInstaller）
```

---

## 📄 更多文档

部署与保密细节见 [`DEPLOY.md`](DEPLOY.md)。