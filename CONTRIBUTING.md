# 🤝 贡献指南

感谢你对 **校园先到先得报名与智能排班系统** 项目的关注！我们欢迎任何形式的贡献。

---

## 📋 目录

- [1. 贡献方式](#1-贡献方式)
- [2. 开发环境](#2-开发环境)
- [3. 代码规范](#3-代码规范)
- [4. 提交规范](#4-提交规范)
- [5. Pull Request 流程](#5-pull-request-流程)
- [6. 报告问题](#6-报告问题)
- [7. 联系方式](#7-联系方式)

---

## 1. 贡献方式

你可以通过以下方式为项目做出贡献：

| 方式 | 说明 |
|------|------|
| 🐛 **报告 Bug** | 发现问题请提交 Issue |
| 💡 **功能建议** | 有好的想法请提交 Issue |
| 📝 **完善文档** | 改进文档、修正错别字 |
| 🧪 **编写测试** | 增加测试覆盖率 |
| 💻 **提交代码** | 修复 Bug 或实现新功能 |

---

## 2. 开发环境

### 2.1 环境要求

- Python 3.9+
- Git
- pip 或 conda

### 2.2 环境搭建

```bash
# 1. Fork 并克隆项目
git clone https://github.com/你的用户名/CampusArrangement.git
cd CampusArrangement

# 2. 添加上游仓库
git remote add upstream https://github.com/LumenAurora/CampusArrangement.git

# 3. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 安装开发依赖（可选）
pip install pytest pytest-cov black flake8 mypy
```

### 2.3 运行项目

```bash
# 本地模式
python -m app.main

# 远程模式
python -m app.api_server  # 终端1
python -m app.main --remote  # 终端2
```

### 2.4 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_registration.py

# 生成覆盖率报告
pytest --cov=app tests/
```

---

## 3. 代码规范

### 3.1 Python 代码风格

- 遵循 [PEP 8](https://peps.python.org/pep-0008/) 规范
- 使用 4 个空格缩进
- 行长度限制为 120 个字符
- 使用类型注解（Type Hints）

### 3.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块名 | 小写下划线 | `user_service.py` |
| 类名 | 大驼峰 | `UserService` |
| 函数名 | 小写下划线 | `get_user_by_id()` |
| 常量 | 大写下划线 | `MAX_RETRY_COUNT` |
| 私有成员 | 单下划线前缀 | `_internal_method()` |

### 3.3 文档规范

- 所有公共类和函数必须有 docstring
- docstring 使用 Google 风格
- 复杂逻辑需要添加注释

```python
def create_user(username: str, password: str, role: UserRole) -> User:
    """
    创建新用户

    Args:
        username: 用户名，3-20个字符
        password: 密码，6-50个字符
        role: 用户角色

    Returns:
        创建的用户对象

    Raises:
        ValueError: 参数校验失败
        DuplicateError: 用户名已存在
    """
    pass
```

### 3.4 代码格式化

```bash
# 使用 Black 格式化代码
black app/ tests/

# 使用 Flake8 检查代码风格
flake8 app/ tests/

# 使用 MyPy 检查类型
mypy app/
```

---

## 4. 提交规范

### 4.1 Commit Message 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 4.2 Type 类型

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 Bug |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（既不是新功能也不是修复） |
| `perf` | 性能优化 |
| `test` | 测试相关 |
| `chore` | 构建工具或辅助工具的变动 |

### 4.3 示例

```bash
# 新功能
git commit -m "feat(registration): 添加小组报名功能"

# 修复 Bug
git commit -m "fix(scheduling): 修复排班算法名额计算错误"

# 文档更新
git commit -m "docs: 更新 README 安装说明"

# 重构
git commit -m "refactor(service): 重构用户服务层代码"
```

---

## 5. Pull Request 流程

### 5.1 提交前检查

- [ ] 代码符合项目规范
- [ ] 所有测试通过
- [ ] 添加了必要的测试
- [ ] 更新了相关文档
- [ ] Commit Message 符合规范

### 5.2 PR 流程

```bash
# 1. 同步上游代码
git fetch upstream
git rebase upstream/master

# 2. 创建特性分支
git checkout -b feature/your-feature

# 3. 进行修改并提交
git add .
git commit -m "feat: 你的修改说明"

# 4. 推送到你的 Fork
git push origin feature/your-feature

# 5. 在 GitHub 上创建 Pull Request
```

### 5.3 PR 描述模板

```markdown
## 描述

简要描述你的修改内容

## 修改类型

- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 重构
- [ ] 其他

## 测试

描述你如何测试你的修改

## 相关 Issue

关联的 Issue 编号（如有）

## 截图（如有）

如果修改了 UI，请提供截图
```

### 5.4 代码审查

- 所有 PR 需要至少 1 个审查者批准
- 审查者可能会要求修改代码
- 请及时响应审查意见

---

## 6. 报告问题

### 6.1 Bug 报告

使用以下模板报告 Bug：

```markdown
## Bug 描述

清晰简洁地描述 Bug

## 复现步骤

1. 执行 '...'
2. 点击 '...'
3. 滚动到 '...'
4. 看到错误

## 预期行为

描述你期望发生的行为

## 实际行为

描述实际发生的行为

## 环境信息

- 操作系统: [如 Windows 11, macOS 13]
- Python 版本: [如 3.10.0]
- 项目版本: [如 v1.0.0]

## 截图

如果适用，添加截图帮助解释问题

## 额外信息

添加任何其他相关信息
```

### 6.2 功能建议

使用以下模板提出功能建议：

```markdown
## 功能描述

清晰简洁地描述你想要的功能

## 使用场景

描述这个功能的使用场景

## 解决方案

描述你期望的解决方案

## 替代方案

描述你考虑过的替代方案

## 额外信息

添加任何其他相关信息
```

---

## 7. 联系方式

| 方式 | 说明 |
|------|------|
| **GitHub Issues** | 提交 Issue |
| **邮箱** | [待添加] |

---

## 📚 相关文档

- [项目设计文档](生活项目：校园先到先得报名与智能排班系统.md)
- [架构设计文档](架构设计文档.md)
- [数据库设计与 API 文档](docs/数据库设计与API文档.md)
- [后端接口文档](docs/后端接口文档.md)

---

<p align="center">
  <strong>感谢你的贡献！🎉</strong>
</p>
