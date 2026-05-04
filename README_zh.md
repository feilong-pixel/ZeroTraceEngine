# ZeroTrace Engine

> 安全、透明、可审计、可回滚的本地文件整理引擎。

ZeroTrace Engine 不是自动清理工具，而是一个本地优先的文件操作工作台。它的目标是在用户明确确认后，把可整理项目移动到项目回收区，并保留可查询、可恢复的操作记录。

## 项目定位

ZeroTrace Engine 遵循以下原则：

- 不做黑箱清理
- 不做静默操作
- 不直接永久删除文件
- 不上传任何本地数据
- 扫描结果、清理计划和回收记录都应可见、可确认、可追溯

## 当前功能

- 扫描本机可整理项目
- 展示路径、大小、来源、分类和风险等级
- 从扫描结果生成清理计划
- 执行清理时移动到 `ZeroTraceRecycle/`
- 支持从回收区恢复到原始路径
- 使用 SQLite 保存扫描结果和清理审计记录
- 提供扫描、清理计划、回收区、审计日志和首页 5 个页面

## 架构分层

当前代码按以下边界组织：

```text
routers/
  只处理 FastAPI 路由、请求模型和响应转发

core/services/
  处理业务编排，例如扫描执行、清理计划执行、回收恢复

core/storage/
  处理 SQLite 连接、建表和 repository 读写

core/scanners/
  只做只读检测，返回结构化 ScanItem

core/utils/
  放置文件移动、回收路径生成等底层辅助能力

static/
  前端页面、页面脚本、样式和 i18n 文案
```

旧入口 `core/scanner.py`、`core/cleaner.py`、`core/recycle.py` 目前保留为兼容层。新代码应优先使用 `core.services.*` 和 `core.storage.*`。

## 安全规则

- 文件清理必须先移动到 `ZeroTraceRecycle/`
- 不使用 `os.remove()`、`Path.unlink()` 或 `shutil.rmtree()` 执行清理
- Restore 前必须检查原路径是否已存在
- Scanner 必须保持只读，不移动、不删除、不写入文件
- Router 不直接调用文件操作或数据库细节
- DB 写入集中在 repository 层

## 技术栈

- Python + FastAPI
- Pydantic
- SQLite
- pathlib / shutil
- 原生 HTML / CSS / JavaScript

## 开发环境

使用既有虚拟环境，不需要新建 venv：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements.txt
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

启动服务：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m uvicorn app:app --reload
```

默认访问：

```text
http://127.0.0.1:8000
```

## 测试

运行当前回归测试：

```powershell
.\test.ps1
```

或直接执行：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pytest -q
```

测试会使用仓库内 `.test-tmp/` 临时目录和隔离 SQLite DB，避免触碰真实系统目录。

## 运行时目录

以下目录是本地运行状态，不应作为源码提交：

```text
data/
logs/
ZeroTraceRecycle/
.test-tmp/
```

## 路线图

- 浏览器缓存扫描
- Windows Update 清理候选检测
- 重复文件检测集成
- 更完整的审计查询
- 更稳定的多语言文案管理

## 理念

系统整理不应该是黑箱行为。用户应该始终知道即将处理什么、已经移动到哪里，以及如何恢复。
