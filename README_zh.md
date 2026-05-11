# ZeroTrace Engine

> 本地文件与注册表清理、可回滚操作引擎。

ZeroTrace Engine 不是 Windows 自动清理工具，而是一个本地优先的清理审阅工作台。它的目标是在用户明确确认后，把可清理的文件移动到项目回收区、把可清理的注册表项写入 `.reg` 备份，并保留可查询、可恢复的操作记录。

## 项目定位

ZeroTrace Engine 遵循以下原则：

- 不做黑箱清理
- 不做静默操作
- 不直接永久删除文件或注册表项
- 不上传任何本地数据
- 扫描结果、清理计划和回收记录都应可见、可确认、可追溯

## 当前功能

### 系统扫描

- 扫描本机可清理项目（临时文件、日志文件、缩略图缓存、Windows Update 缓存、空文件/空文件夹）
- 展示路径、大小、来源、分类和风险等级
- 应用残留扫描能力

### 重复文件检测能力

- 基于 SHA-256 哈希识别重复文件
- 支持图片、视频、文档、压缩包等常见文件类型
- 按哈希分组展示，用户选择保留或清理
- 扫描阶段只读；清理统一进入 `ZeroTraceRecycle/`

### 注册表扫描能力

- 扫描 Windows 注册表中的无效、孤立或损坏条目
- 覆盖六类问题：无效路径引用、孤立 COM 对象、无效卸载记录、失效服务、启动项问题、文件关联损坏
- 四阶段算法：收集键值 → 解析目标路径 → 规则引擎匹配 → 风险评分
- 风险等级：Safe / Medium / High，系统关键项强制标注
- 清理前自动导出 `.reg` 备份文件到 `ZeroTraceRegistryRecycle/`，支持一键恢复（`reg.exe import`）

### 清理计划与回收

- 从扫描结果生成清理计划
- 执行清理计划时移动文件到 `ZeroTraceRecycle/`
- 注册表清理备份写入 `ZeroTraceRegistryRecycle/`
- 支持从回收区恢复文件到原始路径
- 支持从注册表回收区还原注册表项
- 完整的审计日志记录

### 持久化

- SQLite（WAL 模式）保存扫描结果、清理计划、审计记录、文件哈希和设置
- 注册表相关：`registry_scan_results`、`registry_cleanup_plans`、`registry_cleanup_actions` 三张独立表

### 前端

- 多页面：首页、扫描、清理计划、回收区、审计日志、重复文件、注册表扫描、手动工具
- 浏览器 i18n（中/英）无后端依赖
- 原生 JS ES6 模块，无前端框架

## 架构分层

当前代码按以下边界组织：

```text
app.py
  只做 FastAPI 挂载、路由注册、静态文件服务

core/routers/
  只处理 FastAPI 路由、请求模型和响应转发

core/services/
  处理业务编排，例如扫描执行、清理计划执行、回收恢复、注册表扫描与清理

core/storage/
  处理 SQLite 连接、建表和 repository 读写

core/scanners/
  只做只读检测，返回结构化 ScanItem

core/utils/
  放置文件移动、回收路径生成等底层辅助能力

core/models.py
  文件扫描相关 Pydantic 模型

core/registry_models.py
  注册表扫描相关 Pydantic 模型（与文件扫描模型独立）

static/
  前端页面、页面脚本、样式和 i18n 文案
```

新功能应优先放在 `core.services.*`、`core.storage.*` 和 `core.scanners/` 对应边界内，保持路由层、业务层、存储层和扫描层职责清晰。

## 安全规则

- 文件清理必须先移动到 `ZeroTraceRecycle/`，不使用 `os.remove()`、`Path.unlink()` 或 `shutil.rmtree()`
- 注册表清理必须先导出 `.reg` 备份到 `ZeroTraceRegistryRecycle/`，再执行 `winreg.DeleteValue()` / `winreg.DeleteKey()`
- Restore 前必须检查原路径或注册表项是否已存在
- Scanner 必须保持只读，不移动、不删除、不写入
- Router 不直接调用文件操作或数据库细节
- DB 写入集中在 repository 层

## 技术栈

- Python + FastAPI
- Pydantic
- SQLite（WAL 模式）
- `winreg` / `pathlib` / `shutil` / `subprocess`
- 原生 HTML / CSS / JavaScript（无前端框架）

## 开发环境

使用既有虚拟环境，不需要新建 venv：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements.txt
~\.virtualenvs\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

启动服务（热重载）：

```powershell
.\start-dev.ps1
```

或直接：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m uvicorn app:app --reload
```

默认访问：

```text
http://127.0.0.1:8000
```

## 测试

```powershell
.\test.ps1
```

或直接：

```powershell
~\.virtualenvs\venv\Scripts\python.exe -m pytest -q
```

测试会使用仓库内 `.test-tmp/` 临时目录和隔离 SQLite DB，避免触碰真实系统目录。

## 扫描能力

### 临时目录扫描

- 扫描 `C:\Windows\Temp`、用户 `AppData\Local\Temp` 及 `TEMP`/`TMP` 环境变量指向的目录
- 扫描结果去重，默认跳过最近 24 小时内修改的文件

### 日志文件扫描

- 默认扫描仓库 `logs/` 和 Windows 临时目录中的日志
- 识别 `.log`、`.old`、`.bak`、`.tmp` 及常见轮转日志名
- 默认跳过最近 7 天内修改的文件

### 空文件 / 空文件夹扫描

- 仅在低风险根目录中检测空文件和叶子空文件夹
- 默认跳过最近 24 小时内修改的条目

### Windows Update 清理候选检测

- 检测 `C:\Windows\SoftwareDistribution\Download` 下的旧下载缓存
- 默认跳过最近 14 天内修改的文件

### 缩略图缓存扫描

- 检测用户 Windows Explorer 缩略图缓存（`thumbcache_*.db`、`iconcache_*.db`）
- 默认跳过最近 7 天内修改的文件

### 应用残留扫描

- 检测常见 Windows 应用卸载后的遗留文件夹和配置
- 扫描阶段只读，残留项需要进入可回滚清理流程

### 重复文件检测

- 两阶段哈希：快速头部哈希预过滤 + SHA-256 全文哈希确认
- 支持图片、视频、文档、压缩包

### 注册表扫描

- **InvalidPath**：Run/RunOnce 启动项引用路径不存在
- **OrphanCOM**：HKCR\CLSID 注册的 COM 对象 DLL/EXE 已缺失
- **InvalidUninstall**：Uninstall 注册表项中的卸载程序路径不存在
- **InvalidService**：服务注册表项中的执行文件路径不存在
- **StartupIssue**：启动项目标文件损坏或路径格式异常
- **FileAssociation**：文件关联的打开方式程序已缺失

> 所有扫描阶段只读；处理时统一进入对应回收区。之后可从 ZeroTraceEngine 恢复；执行移除时，Windows 会移入系统回收站，其他系统会直接删除。

## 运行时目录

以下目录是本地运行状态，不应作为源码提交：

```text
data/                      # SQLite 数据库文件
logs/                      # 运行时日志
ZeroTraceRecycle/          # 文件回收暂存区
ZeroTraceRegistryRecycle/  # 注册表备份 .reg 文件区
.test-tmp/                 # 测试临时目录
```

## 功能地图

首页按用途把功能入口分为三组：

### 文件清理

| 路径 | 页面 | 作用 | 安全边界 |
|------|------|------|----------|
| `/scan` | 文件扫描 | 扫描临时文件、日志、缩略图缓存、Windows Update 缓存、空文件/空文件夹等清理候选项 | 只读扫描；不会移动文件 |
| `/duplicates` | 重复文件检测 | 扫描指定目录中的重复文件，按哈希分组并选择待清理项 | 只读扫描；选中项进入清理计划 |
| `/user-directory` | 用户目录扫描 | 分析 `%USERPROFILE%` 下的缓存、环境、构建产物、日志和大文件 | 只读扫描；用于空间判断和人工确认 |
| `/cleanup` | 清理计划 | 汇总扫描或重复检测结果，确认后执行清理计划 | 执行时先移动到 `ZeroTraceRecycle/`，保留审计记录 |
| `/recycle` | 回收区 | 查看、恢复或移除进入 `ZeroTraceRecycle/` 的文件 | Restore 回到原路径；Remove 在 Windows 进入系统回收站，其他系统直接删除 |

### 系统检查

| 路径 | 页面 | 作用 | 安全边界 |
|------|------|------|----------|
| `/app-scan` | 应用程序扫描 | 枚举已安装应用、安装目录占用和残留应用线索 | 扫描阶段只读；残留项需进入可回滚流程 |
| `/registry` | 注册表扫描 | 检测无效路径、孤立 COM、无效卸载记录、服务、启动项和文件关联问题 | 清理前导出 `.reg` 备份；高风险和诊断项不会自动执行 |

### 辅助

| 路径 | 页面 | 作用 | 安全边界 |
|------|------|------|----------|
| `/logs` | 审计日志 | 查看整理、恢复、移除、注册表计划等操作记录 | 只读查询 |
| `/tools` | 手动工具 | 提供 Windows 设置、磁盘清理命令和浏览器历史入口 | 外部工具入口；ZeroTraceEngine 不自动执行 |

`/` 为首页，只负责状态概览与功能入口，不执行清理计划操作。

## 路线图

- 注册表扫描规则扩展（MUI 缓存、字体注册等）
- 更完整的审计查询与筛选
- 更多应用残留检测规则
- 回收区批量操作优化

## 理念

系统清理不应该是黑箱行为。用户应该始终知道即将处理什么、已经移动到哪里，以及如何恢复。

## 许可

本项目基于 MIT 许可证开源。详见 [LICENSE](./LICENSE) 文件。
