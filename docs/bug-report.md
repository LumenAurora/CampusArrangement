# 🐛 Bug 审计报告 — CampusArrangement

> 审计日期: 2026-06-27
> 审计范围: 全部源码（domain / application / infrastructure / ui / api_server / tests / tmp_* 文件）
> 审计方法: 静态代码分析 + 架构审查 + 测试覆盖评估

---

## 📊 总览

| 维度 | 数量 |
|------|------|
| 🔴 严重 (Critical) | 5 |
| 🟠 重要 (High) | 12 |
| 🟡 中等 (Medium) | 20 |
| 🔵 轻微 (Low) | 15+ |
| 🧪 测试覆盖缺失 | 15+ 关键路径 |

---

## 🔴 严重 Bug (Critical)

### BUG-001: 排班算法第二轮调整分配忽略用户选择和活动边界
- **文件:** `app/domain/services.py:57-80`
- **描述:** 第一轮分配失败的用户进入"调整轮"。调整算法从整个 `slot_map`（不过滤 `activity_id`）中选取有剩余容量的时段，完全忽略 `reg.slot_id`。
- **影响:** 用户选了"周一上午"可能被分到"周二下午"；多活动场景下可跨活动错分。
- **修复建议:** 调整轮只在用户原选时段满员时才触发，并限制在同一活动的时段内分配。

### BUG-002: 已确认报名取消后时段容量泄漏
- **文件:** `app/application/registration_service.py:108-114`
- **描述:** `cancel()` 只在 `PENDING` 状态下调用 `release_slot`。`CONFIRMED` 状态取消走 `else` 分支，只更新状态不释放 `used_count`。
- **影响:** 时段容量逐渐"枯竭"，实际有空位但显示已满。
- **修复建议:** 取消逻辑应根据活动类型（REALTIME/BLIND）和报名状态，统一释放容量。

### BUG-003: 签到重复保护产生原始数据库错误
- **文件:** `app/infrastructure/repositories.py:638-641`（`CheckInRepository.create`）
- **描述:** 重复签到时 `sqlite3.IntegrityError` 直接抛出，未转换为 `ConflictError`。对比 `RegistrationRepository.create()`（line 422-425）会正确转换。
- **影响:** 并发重复签到时用户看到原始数据库堆栈。
- **修复建议:** 在 `CheckInRepository.create()` 中捕获 `IntegrityError` 并抛 `ConflictError`。

### BUG-004: Remote 模式签到码生成返回错误的码
- **文件:** `app/application/checkin_service.py:220-221`，`app/infrastructure/remote_repositories.py:83-86`
- **描述:** `generate_checkin_code()` 本地生成码并返回。Remote 模式下 `update_checkin_code()` 忽略传入参数，服务器自己生成码。但返回值是本地生成的码。
- **影响:** Remote 模式自助签到永远失败。
- **修复建议:** Remote 模式下从服务器响应中获取签到码并返回。

### BUG-005: 硬编码 admin/admin 默认凭证
- **文件:** `app/api_server.py:65`，`app/main.py:51`
- **描述:** 服务端和客户端自动创建 `admin/admin` 超级管理员，无强制改密。
- **影响:** 未授权用户可获取完整管理员权限。
- **修复建议:** 首次登录强制改密，或从环境变量读取初始密码。

---

## 🟠 重要 Bug (High)

### BUG-006: CORS 允许任意来源携带凭证
- **文件:** `app/api_server.py:35-41`
- **描述:** `allow_origins=["*"]` + `allow_credentials=True` → CSRF 风险。
- **修复建议:** 配置具体允许的 origin 列表。

### BUG-007: ORGANIZER 可创建 SUPER_ADMIN（权限提升）
- **文件:** `app/api_server.py:261-268`
- **描述:** `UserCreateRequest` 接受任意 Role 值，ORGANIZER 可创建 SUPER_ADMIN。
- **修复建议:** 服务端校验创建者角色，限制可创建的角色范围。

### BUG-008: 任意用户可读取所有报名记录
- **文件:** `app/api_server.py:583-588`
- **描述:** `GET /registrations/{id}` 无权限校验。
- **修复建议:** 校验当前用户是否为报名记录所有者或管理员。

### BUG-009: Token 过期后不清除，持续发送过期 Token
- **文件:** `app/infrastructure/api_client.py:65-76`
- **描述:** 收到 401 时抛 `ValidationError` 但不清 `self._token`。
- **修复建议:** 401 响应时自动清除 token 并触发重新登录提示。

### BUG-010: 排班结果查询无权限检查
- **文件:** `app/api_server.py:644-645`
- **描述:** `list_schedules` 按 `activity_id` 查询时无 owner/admin 校验。
- **修复建议:** 添加活动所有者或管理员权限校验。

### BUG-011: 用户状态解析崩溃（authenticate 流程）
- **文件:** `app/application/user_service.py:76`
- **描述:** `UserStatus(record.get("status", "approved"))` 在异常值时抛 `ValueError`。
- **修复建议:** 捕获 `ValueError`，返回认证失败错误。

### BUG-012: 位置签到静默跳过距离校验
- **文件:** `app/application/checkin_service.py:158-168`
- **描述:** location 非 "lat,lon" 格式时 `except: pass` 静默跳过。
- **修复建议:** location 签到模式下，location 必须为有效坐标格式。

### BUG-013: 删除群组导致关联活动不可访问
- **文件:** `app/application/group_service.py:45-51`
- **描述:** `delete_group()` 后 `activities.group_id` 成为悬空引用，`can_access_activity()` 返回 False。
- **修复建议:** 删除群组前将关联活动的 `group_id` 设为 NULL。

### BUG-014: INSERT OR REPLACE 可能降级群组成员
- **文件:** `app/infrastructure/repositories.py:772-778`
- **描述:** `add_member()` 用 `INSERT OR REPLACE`，对已 APPROVED 成员传 PENDING 会静默降级。
- **修复建议:** 改用 `INSERT ... ON CONFLICT DO UPDATE`，仅在新状态优先级更高时更新。

### BUG-015: 活动关闭+排班非原子操作
- **文件:** `app/api_server.py:435-444`
- **描述:** `close_activity` 和 `scheduling_service.run` 在不同事务中。中间崩溃活动卡在 CLOSED 无排班。
- **修复建议:** 在同一事务中执行，或添加补偿机制。

### BUG-016: 创建活动表单无客户端校验，成功后不清空
- **文件:** `app/ui/activity_widgets.py:780-801`
- **描述:** 无前端校验，成功后字段保留可重复提交。
- **修复建议:** 添加客户端校验 + 成功后清空表单。

### BUG-017: UI 中 labelForField 返回 None 时崩溃
- **文件:** `app/ui/activity_widgets.py:571, 576`
- **描述:** `labelForField(self._slot_name).setText(...)` 无空值保护。
- **修复建议:** 添加 `if label:` 守卫。

---

## 🟡 中等问题 (Medium)

| ID | 文件:行号 | 描述 |
|----|-----------|------|
| 018 | `services.py:35` | GREEDY 排序方向歧义（升序 priority 语义不明确） |
| 019 | `services.py:29,33` | FIRST_COME/LOTTERY 忽略 priority 字段 |
| 020 | `models.py:121-154` | `Activity.create()` 无领域级不变量校验 |
| 021 | `activity_service.py:198-208` | CLOSED 活动可删除，孤立报名/排班数据 |
| 022 | `activity_service.py:122-156` | `CUSTOM_OPTION` 和 `SEAT` 枚举已定义但无法创建 |
| 023 | `activity_service.py:146-154` | COURSE 时段创建绕过工厂方法 `create_course()` |
| 024 | `scheduling_service.py:57-61` | 排班后不区分原选时段 vs 被调整时段 |
| 025 | `registration_service.py:41-53` | 时区感知/朴素 datetime 混用（Python 3.14 将报错） |
| 026 | `db.py:14-18` | 无 WAL 模式和连接池 |
| 027 | `db.py:171` | `_ensure_column` 的 `ddl` 参数未校验 |
| 028 | `api_server.py:271,379` | 删除操作用 POST 而非 DELETE |
| 029 | `api_server.py:53` vs `main.py:94` | `RegistrationService` 构造函数签名不一致 |
| 030 | `api_client.py:65-76` | 所有错误统一映射为 `ValidationError` |
| 031 | `activity_widgets.py:895-899` | reopen 失败覆盖原始排班异常 |
| 032 | `activity_widgets.py:660-664` | 表格行内样式表硬编码颜色 |
| 033 | `theme.py:253-256 vs 789-793` | `QLineEdit:focus` 重复定义 |
| 034 | `shell.py:301` | 退出按钮未清除 session/token |
| 035 | `checkin_service.py:240` | `max(0, ...)` 掩盖数据不一致 |
| 036 | `remote_services.py:341-345` | Remote `mark_absent`/`unmark_absent` 返回 None |
| 037 | `remote_repositories.py:237-258` | `RemoteUserRepository` 方法不完整 |

---

## 🧪 测试覆盖缺口

### 现有测试: 16 个（4 文件）

### 完全无测试的模块:
| 模块 | 缺失方法数 |
|------|------------|
| `group_service.py` | 整个模块（create_group, join_group, approve_member 等） |
| `user_service.py` | 7/8 方法 |
| `checkin_service.py` | 7/8 方法 |
| `activity_service.py` | 8/12 方法 |

### 未覆盖关键场景:
1. 并发时段锁定竞态
2. 报名边界时间（恰好在 signup_end）
3. 零容量/负容量时段
4. 群组限制活动报名
5. 重复报名拒绝
6. 非排班用户签到
7. 位置签到距离计算
8. 用户权限边界
9. 排班错误路径
10. BLIND 模式容量管理

---

## 🎨 UI 重塑 (tmp_*) 文件问题

| ID | 文件 | 描述 |
|----|------|------|
| T1 | `tmp_calendar_widgets.py:896` | `_parse_dt` 不处理朴素 datetime，重现已知时区 Bug |
| T2 | `tmp_self_checkin_widgets.py:364` | GPS 坐标硬编码为北京 |
| T3 | `tmp_calendar_widgets.py:288` | 颜色字符串拼接脆弱 |
| T4 | `tmp_calendar_widgets.py:215-223` | WeekView 翻页不发射 date_selected 信号 |
| T5 | `tmp_user_admin_widgets.py:110` | Repository 直接实例化，无法注入测试替身 |
| T6 | `tmp_ui_utils_03ab37d.py` | 缺少多个关键函数 |
| T7 | `tmp_ui_utils_*.py` | 中文字符串乱码（编码错误） |
| T8 | `tmp_reg_widgets.py:499-505` | 异常处理不捕获通用 Exception |

---

## 📋 事件链路风险

### 创建→发布→报名→关闭→排班→签到
- 排班调整不尊重用户选择 (BUG-001)
- 关闭+排班非原子 (BUG-015)
- 已确认取消不释放容量 (BUG-002)

### Remote 模式通信
- 签到码不一致 (BUG-004)
- mark_absent 返回 None (036)
- RemoteUserRepository 不完整 (037)
- Token 过期不清理 (BUG-009)

### 多端并发
- 无 WAL 模式 (026)
- Token 清理竞态 (BUG-009)
- 报名重复检查在事务外 (025)
- MetricsCache 非线程安全 (037)

---

## 🎯 修复优先级

### P0 — 立即修复
1. BUG-002: 确认报名取消释放容量
2. BUG-003: CheckInRepository IntegrityError → ConflictError
3. BUG-004: Remote 签到码返回值
4. BUG-001: 排班算法第二轮尊重用户选择
5. BUG-005: 移除硬编码凭证

### P1 — 尽快修复
6. BUG-006/007/008: CORS、权限提升、信息泄露
7. BUG-009: Token 过期清除
8. BUG-013: 群组删除清理
9. BUG-016: 表单校验 + 清空

### P2 — 计划修复
10. 所有 Medium 级问题
11. 补充关键路径单元测试
12. tmp 文件 Bug 修复后合入
