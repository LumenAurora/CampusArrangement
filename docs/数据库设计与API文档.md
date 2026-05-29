# 🗄️ 数据库设计与 API 文档

> **版本**: v1.0  
> **更新日期**: 2026-05-29  
> **数据库**: SQLite  
> **文档状态**: 正式版

---

## 📋 目录

- [1. 数据库概述](#1-数据库概述)
- [2. ER 图](#2-er-图)
- [3. 表结构设计](#3-表结构设计)
- [4. 仓储 API](#4-仓储-api)
- [5. 事务与并发控制](#5-事务与并发控制)
- [6. 字段与枚举约定](#6-字段与枚举约定)
- [7. 数据迁移指南](#7-数据迁移指南)
- [8. 维护注意事项](#8-维护注意事项)

---

## 1. 数据库概述

### 1.1 数据库定位

当前项目使用 **SQLite** 作为默认持久化方案，具有以下特点：

| 特性 | 说明 |
|------|------|
| **轻量级** | 无需额外安装配置，Python 原生支持 |
| **零配置** | 数据库文件即服务，开箱即用 |
| **单文件** | 数据库存储在单个文件中，便于备份和迁移 |
| **事务支持** | 支持 ACID 事务，保证数据一致性 |

### 1.2 配置说明

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| 数据库路径 | `CAMPUS_DB_PATH` | `app/resources/data/app.db` | SQLite 数据库文件路径 |
| 连接超时 | `DB_TIMEOUT` | `30` | 连接超时时间（秒） |
| 日志模式 | `DB_JOURNAL_MODE` | `WAL` | 日志模式，WAL 性能更优 |

### 1.3 架构位置

```
┌─────────────────────────────────────────────────────────┐
│                      UI 层                               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    应用服务层                             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    仓储层 (Repository)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   UserRepo  │  │ ActivityRepo│  │ ScheduleRepo│     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              SQLite 数据库 (app.db)                      │
└─────────────────────────────────────────────────────────┘
```

**关键设计:**
- 数据库访问不直接暴露给 UI，而是通过仓储层完成
- 仓储层提供统一的数据访问接口，支持本地/远程切换
- 上层代码不感知底层数据库实现

---

## 2. ER 图

### 2.1 实体关系图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据库 ER 图                                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│    users     │         │  activities  │         │    slots     │
├──────────────┤         ├──────────────┤         ├──────────────┤
│ id (PK)      │◄───┐    │ id (PK)      │◄───┐    │ id (PK)      │
│ username     │    │    │ name         │    ├───►│ activity_id  │
│ role         │    │    │ status       │    │    │ start_time   │
│ password_hash│    │    │ owner_id ────┼────┘    │ end_time     │
│ created_at   │    │    │ signup_start │         │ capacity     │
└──────────────┘    │    │ signup_end   │         │ used_count   │
       │            │    │ details      │         └──────────────┘
       │            │    │ signup_mode  │                │
       │            │    │ allocation   │                │
       │            │    └──────────────┘                │
       │            │           │                        │
       │            │           ▼                        │
       │            │    ┌──────────────┐                │
       │            │    │registrations │                │
       │            │    ├──────────────┤                │
       │            └───►│ user_id      │                │
       │                 │ activity_id  │                │
       │                 │ slot_id ─────┼────────────────┘
       │                 │ priority     │
       │                 │ status       │
       │                 │ created_at   │
       │                 └──────────────┘
       │                        │
       │                        ▼
       │                 ┌──────────────┐
       │                 │schedule_result│
       │                 ├──────────────┤
       └────────────────►│ user_id      │
                         │ activity_id  │
                         │ slot_id      │
                         │ created_at   │
                         └──────────────┘
```

### 2.2 关系说明

| 关系 | 类型 | 说明 |
|------|------|------|
| users → activities | 一对多 | 一个用户可以创建多个活动（owner_id） |
| activities → slots | 一对多 | 一个活动可以有多个时段 |
| users → registrations | 一对多 | 一个用户可以有多条报名记录 |
| activities → registrations | 一对多 | 一个活动可以有多条报名记录 |
| slots → registrations | 一对多 | 一个时段可以有多条报名记录 |
| users → schedule_results | 一对多 | 一个用户可以有多个排班结果 |
| activities → schedule_results | 一对多 | 一个活动可以有多个排班结果 |
| slots → schedule_results | 一对多 | 一个时段可以有多个排班结果 |

---

## 3. 表结构设计

### 3.1 users 表

**用途:** 存储用户信息和认证凭证

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 用户 ID，UUID 格式 |
| `username` | TEXT | UNIQUE, NOT NULL | 用户名，用于登录 |
| `role` | TEXT | NOT NULL | 角色，值来自 Role 枚举 |
| `password_hash` | TEXT | NOT NULL | 密码哈希值（bcrypt） |
| `created_at` | TEXT | NOT NULL | 创建时间，ISO8601 格式 |

**索引:**
- `idx_users_username` - username 唯一索引
- `idx_users_role` - role 普通索引

**SQL 定义:**
```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
```

---

### 3.2 activities 表

**用途:** 存储活动信息和配置

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 活动 ID，UUID 格式 |
| `name` | TEXT | NOT NULL | 活动名称 |
| `status` | TEXT | NOT NULL | 活动状态，值来自 ActivityStatus 枚举 |
| `owner_id` | TEXT | FOREIGN KEY | 创建者 ID，关联 users.id |
| `signup_start` | TEXT | | 报名开始时间，ISO8601 格式 |
| `signup_end` | TEXT | | 报名结束时间，ISO8601 格式 |
| `details` | TEXT | | 活动说明 |
| `signup_mode` | TEXT | DEFAULT 'realtime' | 报名模式 |
| `allocation_mode` | TEXT | DEFAULT 'greedy' | 排班模式 |

**索引:**
- `idx_activities_owner` - owner_id 普通索引
- `idx_activities_status` - status 普通索引
- `idx_activities_signup_end` - signup_end 普通索引

**SQL 定义:**
```sql
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    owner_id TEXT REFERENCES users(id),
    signup_start TEXT,
    signup_end TEXT,
    details TEXT,
    signup_mode TEXT DEFAULT 'realtime',
    allocation_mode TEXT DEFAULT 'greedy'
);

CREATE INDEX IF NOT EXISTS idx_activities_owner ON activities(owner_id);
CREATE INDEX IF NOT EXISTS idx_activities_status ON activities(status);
CREATE INDEX IF NOT EXISTS idx_activities_signup_end ON activities(signup_end);
```

---

### 3.3 slots 表

**用途:** 存储活动时段信息

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 时段 ID，UUID 格式 |
| `activity_id` | TEXT | FOREIGN KEY, NOT NULL | 关联活动 ID，关联 activities.id |
| `start_time` | TEXT | NOT NULL | 开始时间，ISO8601 格式 |
| `end_time` | TEXT | NOT NULL | 结束时间，ISO8601 格式 |
| `capacity` | INTEGER | NOT NULL | 总容量（名额上限） |
| `used_count` | INTEGER | DEFAULT 0 | 已使用名额 |

**索引:**
- `idx_slots_activity` - activity_id 普通索引

**SQL 定义:**
```sql
CREATE TABLE IF NOT EXISTS slots (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    capacity INTEGER NOT NULL,
    used_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_slots_activity ON slots(activity_id);
```

---

### 3.4 registrations 表

**用途:** 存储用户报名记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 报名记录 ID，UUID 格式 |
| `user_id` | TEXT | FOREIGN KEY, NOT NULL | 用户 ID，关联 users.id |
| `activity_id` | TEXT | FOREIGN KEY, NOT NULL | 活动 ID，关联 activities.id |
| `slot_id` | TEXT | FOREIGN KEY, NOT NULL | 时段 ID，关联 slots.id |
| `priority` | INTEGER | NOT NULL | 志愿优先级（1-3） |
| `status` | TEXT | NOT NULL | 报名状态，值来自 RegistrationStatus 枚举 |
| `created_at` | TEXT | NOT NULL | 创建时间，ISO8601 格式 |

**索引:**
- `idx_registrations_user` - user_id 普通索引
- `idx_registrations_activity` - activity_id 普通索引
- `idx_registrations_slot` - slot_id 普通索引
- `idx_registrations_status` - status 普通索引

**唯一约束:**
- `uq_registration_user_slot` - 同一用户同一时段只能报名一次

**SQL 定义:**
```sql
CREATE TABLE IF NOT EXISTS registrations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    activity_id TEXT NOT NULL REFERENCES activities(id),
    slot_id TEXT NOT NULL REFERENCES slots(id),
    priority INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, slot_id)
);

CREATE INDEX IF NOT EXISTS idx_registrations_user ON registrations(user_id);
CREATE INDEX IF NOT EXISTS idx_registrations_activity ON registrations(activity_id);
CREATE INDEX IF NOT EXISTS idx_registrations_slot ON registrations(slot_id);
CREATE INDEX IF NOT EXISTS idx_registrations_status ON registrations(status);
```

---

### 3.5 schedule_results 表

**用途:** 存储排班结果

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PRIMARY KEY | 排班结果 ID，UUID 格式 |
| `activity_id` | TEXT | FOREIGN KEY, NOT NULL | 活动 ID，关联 activities.id |
| `user_id` | TEXT | FOREIGN KEY, NOT NULL | 用户 ID，关联 users.id |
| `slot_id` | TEXT | FOREIGN KEY, NOT NULL | 分配时段 ID，关联 slots.id |
| `created_at` | TEXT | NOT NULL | 创建时间，ISO8601 格式 |

**索引:**
- `idx_schedule_activity` - activity_id 普通索引
- `idx_schedule_user` - user_id 普通索引

**唯一约束:**
- `uq_schedule_user_activity` - 同一用户在同一活动只有一个排班结果

**SQL 定义:**
```sql
CREATE TABLE IF NOT EXISTS schedule_results (
    id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL REFERENCES activities(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    slot_id TEXT NOT NULL REFERENCES slots(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, activity_id)
);

CREATE INDEX IF NOT EXISTS idx_schedule_activity ON schedule_results(activity_id);
CREATE INDEX IF NOT EXISTS idx_schedule_user ON schedule_results(user_id);
```

---

## 4. 仓储 API

### 4.1 UserRepository

**职责:** 用户数据访问

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_by_id` | `user_id: str` | `Optional[dict]` | 按 ID 查询用户 |
| `get_by_username` | `username: str` | `Optional[dict]` | 按用户名查询用户 |
| `list_all` | - | `List[dict]` | 返回用户列表 |
| `create` | `user: dict, password_hash: str` | `dict` | 创建用户 |

**使用示例:**
```python
# 获取用户
user_repo = UserRepository(db)
user = user_repo.get_by_id("user-001")

# 创建用户
new_user = user_repo.create({
    "username": "user01",
    "role": "user"
}, password_hash="hashed_password")
```

---

### 4.2 ActivityRepository

**职责:** 活动数据访问

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `create` | `activity: dict` | `dict` | 创建活动 |
| `get` | `activity_id: str` | `Optional[dict]` | 按 ID 查询活动 |
| `list_all` | - | `List[dict]` | 按报名开始时间倒序返回活动列表 |
| `count_all` | - | `int` | 统计活动总数 |
| `update_status` | `activity_id: str, status: str` | `bool` | 更新活动状态 |

**使用示例:**
```python
# 创建活动
activity_repo = ActivityRepository(db)
activity = activity_repo.create({
    "name": "志愿服务活动",
    "owner_id": "user-001",
    "signup_start": "2026-05-29T08:00:00",
    "signup_end": "2026-05-30T18:00:00"
})

# 查询活动
activity = activity_repo.get("activity-001")
```

---

### 4.3 TimeSlotRepository

**职责:** 时段数据访问

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `create` | `slot: dict` | `dict` | 创建时段 |
| `list_by_activity` | `activity_id: str` | `List[dict]` | 查询活动下所有时段 |
| `count_all` | - | `int` | 统计时段总数 |
| `lock_slot` | `slot_id: str` | `bool` | 原子扣减名额，成功返回 `True` |
| `unlock_slot` | `slot_id: str` | `bool` | 释放名额 |

**使用示例:**
```python
# 创建时段
slot_repo = TimeSlotRepository(db)
slot = slot_repo.create({
    "activity_id": "activity-001",
    "start_time": "2026-05-31T09:00:00",
    "end_time": "2026-05-31T12:00:00",
    "capacity": 30
})

# 锁定名额
success = slot_repo.lock_slot("slot-001")
if success:
    print("名额锁定成功")
else:
    print("名额已满")
```

**并发控制:**
- `lock_slot` 使用 `BEGIN IMMEDIATE` 事务
- 先检查容量，再执行原子更新
- 返回 `False` 表示名额已满

---

### 4.4 RegistrationRepository

**职责:** 报名记录数据访问

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `create` | `registration: dict` | `dict` | 创建报名记录 |
| `list_pending` | `activity_id: str` | `List[dict]` | 查询待排班报名记录 |
| `count_all` | - | `int` | 统计报名总数 |
| `count_by_user` | `user_id: str` | `int` | 统计用户报名数 |
| `update_status` | `registration_id: str, status: str` | `bool` | 更新报名状态 |

**使用示例:**
```python
# 创建报名记录
reg_repo = RegistrationRepository(db)
registration = reg_repo.create({
    "user_id": "user-001",
    "activity_id": "activity-001",
    "slot_id": "slot-001",
    "priority": 1
})

# 查询待排班记录
pending = reg_repo.list_pending("activity-001")
```

---

### 4.5 ScheduleRepository

**职责:** 排班结果数据访问

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `create` | `result: dict` | `dict` | 创建排班结果 |
| `clear_for_activity` | `activity_id: str` | `int` | 清空指定活动的排班结果，返回删除数量 |
| `list_by_activity` | `activity_id: str` | `List[dict]` | 查询活动排班结果 |
| `list_by_user` | `user_id: str` | `List[dict]` | 查询用户排班结果 |
| `count_all` | - | `int` | 统计排班结果总数 |
| `count_by_user` | `user_id: str` | `int` | 统计用户排班结果数 |

**使用示例:**
```python
# 创建排班结果
schedule_repo = ScheduleRepository(db)
result = schedule_repo.create({
    "activity_id": "activity-001",
    "user_id": "user-001",
    "slot_id": "slot-001"
})

# 查询用户排班结果
results = schedule_repo.list_by_user("user-001")
```

**幂等性保证:**
- 排班结果写入前会先清空该活动旧结果
- 保证重复执行排班不会产生重复数据

---

## 5. 事务与并发控制

### 5.1 事务机制

```
┌─────────────────────────────────────────────────────────────┐
│                    事务执行流程                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐ │
│  │ BEGIN   │ ─► │ 检查    │ ─► │ 执行    │ ─► │ COMMIT  │ │
│  │IMMEDIATE│    │ 容量    │    │ 更新    │    │         │ │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘ │
│       │              │              │              │        │
│       │              │              │              │        │
│       ▼              ▼              ▼              ▼        │
│   获取写锁      容量足够？      更新used_count   提交事务   │
│                       │                                    │
│                       ▼                                    │
│                  ┌─────────┐                               │
│                  │ ROLLBACK│                               │
│                  └─────────┘                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 名额锁定流程

```python
def lock_slot(db, slot_id: str) -> bool:
    """
    原子扣减名额
    
    流程:
    1. BEGIN IMMEDIATE - 获取写锁
    2. 检查容量是否足够
    3. 执行更新
    4. COMMIT 或 ROLLBACK
    """
    try:
        db.execute("BEGIN IMMEDIATE")
        
        # 检查容量
        cursor = db.execute(
            "SELECT capacity, used_count FROM slots WHERE id = ?",
            (slot_id,)
        )
        row = cursor.fetchone()
        
        if row["used_count"] >= row["capacity"]:
            db.execute("ROLLBACK")
            return False
        
        # 执行更新
        db.execute(
            "UPDATE slots SET used_count = used_count + 1 WHERE id = ?",
            (slot_id,)
        )
        
        db.execute("COMMIT")
        return True
        
    except Exception:
        db.execute("ROLLBACK")
        raise
```

### 5.3 并发场景处理

| 场景 | 问题 | 解决方案 |
|------|------|---------|
| **并发报名** | 多个用户同时抢同一个名额 | `BEGIN IMMEDIATE` 事务 + 容量检查 |
| **超时释放** | 用户报名后未确认，名额被占用 | 定时任务检查超时记录，自动释放名额 |
| **重复报名** | 同一用户重复报名同一时段 | `UNIQUE(user_id, slot_id)` 约束 |
| **排班重跑** | 重新排班产生重复结果 | 先清空旧结果，再写入新结果 |

---

## 6. 字段与枚举约定

### 6.1 角色枚举 (Role)

| 值 | 说明 | 权限范围 |
|----|------|---------|
| `super_admin` | 超级管理员 | 全局权限 |
| `organizer` | 活动组织者 | 管理自有活动 |
| `user` | 普通用户 | 报名参与活动 |

### 6.2 活动状态枚举 (ActivityStatus)

| 值 | 说明 | 可执行操作 |
|----|------|-----------|
| `draft` | 草稿 | 编辑、发布 |
| `open` | 报名中 | 报名、查看 |
| `closed` | 报名结束 | 排班、查看 |
| `archived` | 已归档 | 查看 |

### 6.3 报名模式枚举 (SignupMode)

| 值 | 说明 |
|----|------|
| `realtime` | 实时模式，报名时立即锁定名额 |
| `blind` | 盲报模式，报名截止后统一处理 |

### 6.4 排班模式枚举 (AllocationMode)

| 值 | 说明 |
|----|------|
| `greedy` | 贪心算法，按报名时间+志愿优先级分配 |
| `first_come` | 先到先得，按报名时间顺序分配 |
| `lottery` | 抽签模式，随机分配 |

### 6.5 报名状态枚举 (RegistrationStatus)

| 值 | 说明 |
|----|------|
| `pending` | 待处理 |
| `confirmed` | 已确认（实时模式） |
| `assigned` | 已分配（排班后） |
| `cancelled` | 已取消 |

---

## 7. 数据迁移指南

### 7.1 迁移原则

| 原则 | 说明 |
|------|------|
| **兼容性优先** | 新版本必须兼容旧版本数据 |
| **不删表** | 禁止直接删除表结构，使用 ALTER TABLE |
| **备份优先** | 迁移前必须备份数据库 |
| **可回滚** | 迁移脚本必须支持回滚 |

### 7.2 迁移脚本模板

```python
def migrate_v1_to_v2(db):
    """
    数据库迁移脚本 v1 -> v2
    """
    # 1. 备份原表
    db.execute("""
        CREATE TABLE IF NOT EXISTS users_backup AS 
        SELECT * FROM users
    """)
    
    # 2. 创建新表
    db.execute("""
        CREATE TABLE IF NOT EXISTS users_new (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            password_hash TEXT NOT NULL,
            email TEXT,  -- 新增字段
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    
    # 3. 迁移数据
    db.execute("""
        INSERT INTO users_new (id, username, role, password_hash, created_at)
        SELECT id, username, role, password_hash, created_at FROM users
    """)
    
    # 4. 重命名表
    db.execute("DROP TABLE users")
    db.execute("ALTER TABLE users_new RENAME TO users")
    
    # 5. 验证数据
    count_old = db.execute("SELECT COUNT(*) FROM users_backup").fetchone()[0]
    count_new = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    assert count_old == count_new, "数据迁移失败，记录数不一致"
    
    # 6. 清理备份（可选）
    # db.execute("DROP TABLE users_backup")
```

### 7.3 常见迁移操作

| 操作 | SQL 语句 |
|------|---------|
| 添加字段 | `ALTER TABLE table_name ADD COLUMN column_name type` |
| 重命名表 | `ALTER TABLE old_name RENAME TO new_name` |
| 创建索引 | `CREATE INDEX IF NOT EXISTS idx_name ON table(column)` |
| 删除索引 | `DROP INDEX IF EXISTS idx_name` |

---

## 8. 维护注意事项

### 8.1 日常维护

| 项目 | 频率 | 操作 |
|------|------|------|
| **备份数据库** | 每日 | 复制 app.db 文件 |
| **清理过期数据** | 每月 | 删除已归档活动的历史数据 |
| **检查索引** | 每周 | 分析查询性能，必要时添加索引 |
| **Vacuum** | 每月 | 执行 `VACUUM` 命令回收空间 |

### 8.2 性能优化

| 优化项 | 方法 |
|--------|------|
| **查询优化** | 使用 EXPLAIN QUERY PLAN 分析查询计划 |
| **索引优化** | 为常用查询字段添加索引 |
| **连接池** | 使用连接池减少连接开销 |
| **批量操作** | 使用事务包裹批量操作 |

### 8.3 安全建议

| 建议 | 说明 |
|------|------|
| **密码加密** | 使用 bcrypt 或 argon2 加密密码 |
| **SQL 注入** | 使用参数化查询，禁止字符串拼接 |
| **权限控制** | 限制数据库文件访问权限 |
| **审计日志** | 记录关键操作的日志 |

---

## 📚 相关文档

- [项目设计文档](../生活项目：校园先到先得报名与智能排班系统.md) - 项目背景、功能模块
- [架构设计文档](../架构设计文档.md) - 系统架构、分层设计
- [后端接口文档](后端接口文档.md) - FastAPI 接口详细说明

---

<p align="center">
  <strong>📝 文档维护者: LumenAurora</strong>
</p>
