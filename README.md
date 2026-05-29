# 🎓 校园先到先得报名与智能排班系统

<p align="center">
  <strong>CampusArrangement</strong>
</p>

<p align="center">
  一个基于 PySide6 + FastAPI 的校园活动报名与智能排班桌面应用
</p>

---

## 📖 项目简介

校园场景中，志愿服务报名、课堂 Pre 名额预约、活动时段排班等需求高频出现。现有工具（问卷星、Excel、微信群）存在以下痛点：

- ❌ 无法实现精准的先到先得名额锁定，易出现超报、抢票混乱
- ❌ 不支持多志愿调剂与自动排班，组织者需手动统计协调
- ❌ 无分层权限管理，无法区分管理员、组织者、参与者的操作边界

本项目打造 **「报名-锁额-调剂-排班-导出」** 全流程闭环，完全贴合校园真实场景。

---

## ✨ 核心功能

| 功能模块 | 描述 |
|---------|------|
| 🔐 三级权限管理 | 超级管理员、活动组织者、普通用户分级权限控制 |
| 📝 活动创建与配置 | 支持多时段、多规则配置，可视化操作 |
| ⚡ 先到先得报名 | 实时锁定名额，支持小组报名，自动超时释放 |
| 🎯 多志愿调剂 | 报名截止后自动匹配第二/第三志愿，保证公平 |
| 📊 智能排班 | 基于贪心算法自动生成均衡排班表 |
| 📁 数据导出 | 一键导出 Excel 报名名单、排班表 |
| 📈 数据统计 | 报名率、时段饱和度、调剂成功率可视化 |

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    PySide6 桌面客户端                      │
├─────────────────────────────────────────────────────────┤
│                    应用服务层 (Application)                │
├─────────────────────────────────────────────────────────┤
│                    领域层 (Domain)                        │
├─────────────────────────────────────────────────────────┤
│          基础设施层 (SQLite / FastAPI / Exporter)          │
└─────────────────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 技术选型 |
|------|---------|
| 前端 | PySide6 (Qt for Python) |
| 后端 | FastAPI + Uvicorn |
| 数据库 | SQLite |
| 数据处理 | Pandas + OpenPyXL |
| 认证 | JWT Token + Passlib |

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- pip 或 conda

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/LumenAurora/CampusArrangement.git
cd CampusArrangement

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动应用（本地模式）
python -m app.main

# 5. 启动应用（远程模式，需要先启动后端）
python -m app.api_server  # 终端1：启动 FastAPI 后端
python -m app.main --remote  # 终端2：启动客户端
```

### 默认账户

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 超级管理员 | admin | admin |
| 普通用户 | user01 | 123456 |

---

## 📁 项目结构

```
CampusArrangement/
├── app/                          # 应用主目录
│   ├── ui/                       # PySide6 界面层
│   │   ├── main_window.py        # 主窗口
│   │   ├── login_dialog.py       # 登录对话框
│   │   ├── activity_widgets.py   # 活动管理组件
│   │   ├── registration_widgets.py # 报名管理组件
│   │   ├── scheduling_widgets.py # 排班管理组件
│   │   └── ...
│   ├── application/              # 应用服务层
│   │   ├── user_service.py       # 用户服务
│   │   ├── activity_service.py   # 活动服务
│   │   ├── registration_service.py # 报名服务
│   │   ├── scheduling_service.py # 排班服务
│   │   └── remote_services.py    # 远程服务适配
│   ├── domain/                   # 领域层
│   │   ├── models.py             # 数据模型
│   │   ├── enums.py              # 枚举定义
│   │   └── scheduler.py          # 排班算法
│   ├── infrastructure/           # 基础设施层
│   │   ├── db.py                 # SQLite 数据库
│   │   ├── auth.py               # 认证模块
│   │   ├── exporter.py           # Excel 导出
│   │   └── api_client.py         # HTTP 客户端
│   ├── main.py                   # 应用入口
│   ├── api_server.py             # FastAPI 服务端
│   └── config.py                 # 配置管理
├── docs/                         # 文档目录
│   ├── 数据库设计与API文档.md
│   └── 后端接口文档.md
├── tests/                        # 测试代码
├── scripts/                      # 脚本工具
├── requirements.txt              # Python 依赖
├── 架构设计文档.md                 # 架构设计文档
└── 生活项目：校园先到先得报名与智能排班系统.md  # 项目设计文档
```

---

## 📚 文档导航

| 文档 | 说明 |
|------|------|
| [项目设计文档](生活项目：校园先到先得报名与智能排班系统.md) | 项目背景、功能模块、技术选型、开发计划 |
| [架构设计文档](架构设计文档.md) | 系统架构、分层设计、业务规则 |
| [数据库设计与API文档](docs/数据库设计与API文档.md) | 数据库表结构、接口设计 |
| [后端接口文档](docs/后端接口文档.md) | FastAPI 接口详细说明 |

---

## 🎯 设计模式

本项目应用了以下经典设计模式：

| 模式 | 应用场景 |
|------|---------|
| **工厂模式** | 创建不同角色的用户对象 |
| **单例模式** | 管理全局登录状态与权限校验 |
| **状态模式** | 管理活动全生命周期（未开始、报名中、已结束、已归档） |
| **观察者模式** | 名额变化的实时更新与通知 |
| **策略模式** | 不同的排班算法切换 |
| **仓储模式** | 数据访问层抽象，支持本地/远程切换 |

---

## 🔧 配置说明

### 运行模式

系统支持两种运行模式：

1. **本地模式**：PySide6 客户端直接访问 SQLite，适合单机使用
2. **远程模式**：PySide6 客户端通过 HTTP 调用 FastAPI 后端，适合多用户场景

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `APP_MODE` | 运行模式 (local/remote) | local |
| `DB_PATH` | SQLite 数据库路径 | data/campus.db |
| `API_HOST` | API 服务地址 | 127.0.0.1 |
| `API_PORT` | API 服务端口 | 8000 |
| `SECRET_KEY` | JWT 密钥 | 自动生成 |

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_registration.py

# 生成覆盖率报告
pytest --cov=app tests/
```

---

## 📦 打包部署

```bash
# 使用 PyInstaller 打包为可执行文件
pyinstaller --onefile --windowed app/main.py
```

---

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 👥 作者

- **LumenAurora** - [GitHub](https://github.com/LumenAurora)

---

## 🙏 致谢

- [PySide6](https://wiki.qt.io/Qt_for_Python) - Qt for Python
- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能 Web 框架
- [SQLite](https://www.sqlite.org/) - 轻量级数据库
- [Pandas](https://pandas.pydata.org/) - 数据分析库

---

<p align="center">
  ⭐ 如果这个项目对你有帮助，请给个 Star 支持一下！
</p>
