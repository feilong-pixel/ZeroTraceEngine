# ZeroTrace Engine

> 安全、透明、可审计、可回滚的本地系统整理引擎

---

## 🧩 项目定位

ZeroTrace Engine 是一个 **工程师风格的系统整理工具**：

- ❌ 不做黑箱清理
- ❌ 不做自动删除
- ❌ 不上传任何数据

- ✅ 所有文件可见
- ✅ 所有操作可控
- ✅ 所有删除可恢复

---

## ⚙️ 核心原则

- **透明（Transparent）**
  - 所有扫描结果都展示完整路径 / 大小 / 来源

- **可控（Controllable）**
  - 每一项清理操作都由用户决定

- **可逆（Reversible）**
  - 所有删除行为进入 `ZeroTraceRecycle/`
  - 支持恢复 + 审计

---

## 🏗️ 架构

```text
ScanEngine   → 扫描系统垃圾
Analyzer     → 分析空间占用 & 建议
CleanEngine  → 安全移动（不删除）
RecycleBin   → 恢复系统
AuditLog     → 审计日志（SQLite）
````

---

## 📦 v0.1 功能范围

* 扫描系统临时文件
* 展示扫描结果
* 生成清理计划
* 安全移动到回收区
* SQLite 审计日志

---

## 🧱 技术栈

* Python + FastAPI
* Pydantic
* SQLite
* Pathlib / shutil
* 原生 HTML / CSS / JS

---

## 🚀 启动方式

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

打开：

```
http://127.0.0.1:8000
```

---

## 📂 回收区

所有删除操作不会直接删除：

```
ZeroTraceRecycle/
```

支持恢复与审计。

---

## ⚠️ 安全声明

ZeroTrace Engine：

* 不自动删除任何文件
* 不访问网络
* 不上传用户数据
* 所有操作需用户确认

---

## 🛣️ Roadmap

* [ ] 浏览器缓存扫描
* [ ] Windows Update 清理
* [ ] 重复文件检测集成
* [ ] 可视化分析面板
* [ ] 插件系统

---

## 🧠 理念

> 系统整理不应该是黑箱行为
> 用户应该拥有对数据的完全控制权

````
