# 数据库设计与 API 文档

## 1. 数据库定位
当前项目使用 SQLite 作为默认持久化方案，数据库文件路径由环境变量 `CAMPUS_DB_PATH` 控制，默认位于 `app/resources/data/app.db`。

数据库访问不直接暴露给 UI，而是通过仓储层完成。

## 2. 表结构

### 2.1 users
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | 用户 ID |
| username | TEXT UNIQUE | 用户名 |
| role | TEXT | 角色，值来自 Role 枚举 |
| password_hash | TEXT | 密码哈希 |
| created_at | TEXT | 创建时间，ISO8601 |

### 2.2 activities
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | 活动 ID |
| name | TEXT | 活动名称 |
| status | TEXT | 活动状态 |
| owner_id | TEXT | 创建者 ID |
| signup_start | TEXT | 报名开始时间 |
| signup_end | TEXT | 报名结束时间 |
| details | TEXT | 活动说明 |
| signup_mode | TEXT | 报名模式，默认 realtime |
| allocation_mode | TEXT | 排班模式，默认 greedy |

### 2.3 slots
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | 时段 ID |
| activity_id | TEXT | 关联活动 ID |
| start_time | TEXT | 开始时间 |
| end_time | TEXT | 结束时间 |
| capacity | INTEGER | 总容量 |
| used_count | INTEGER | 已使用名额 |

### 2.4 registrations
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | 报名记录 ID |
| user_id | TEXT | 用户 ID |
| activity_id | TEXT | 活动 ID |
| slot_id | TEXT | 时段 ID |
| priority | INTEGER | 志愿优先级 |
| status | TEXT | 报名状态 |
| created_at | TEXT | 创建时间 |

### 2.5 schedule_results
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | 排班结果 ID |
| activity_id | TEXT | 活动 ID |
| user_id | TEXT | 用户 ID |
| slot_id | TEXT | 分配时段 ID |
| created_at | TEXT | 创建时间 |

## 3. 仓储 API

### 3.1 UserRepository
- `get_by_id(user_id)`：按 ID 查询用户
- `get_by_username(username)`：按用户名查询用户
- `list_all()`：返回用户列表
- `create(user, password_hash)`：创建用户
- `delete(user_id)`：删除用户

### 3.2 ActivityRepository
- `create(activity)`：创建活动
- `get(activity_id)`：按 ID 查询活动
- `list_all()`：按报名开始时间倒序返回活动列表
- `count_all()`：统计活动总数
- `delete(activity_id)`：删除活动

### 3.3 TimeSlotRepository
- `get(slot_id)`：按 ID 查询时段
- `create(slot)`：创建时段
- `list_by_activity(activity_id)`：查询活动下所有时段
- `count_all()`：统计时段总数
- `lock_slot(slot_id)`：原子扣减名额，成功返回 `True`
- `release_slot(slot_id)`：释放名额（`used_count` 减 1，不低于 0）

### 3.4 RegistrationRepository
- `create(registration)`：创建报名记录
- `list_pending(activity_id)`：查询待排班报名记录
- `list_by_user_activity(user_id, activity_id)`：查询用户对某活动的报名记录
- `update_status(registration_id, status)`：更新报名状态
- `count_all()`：统计报名总数
- `count_by_user(user_id)`：统计用户报名数

### 3.5 ScheduleRepository
- `create(result)`：创建排班结果
- `clear_for_activity(activity_id)`：清空指定活动的排班结果
- `list_by_activity(activity_id)`：查询活动排班结果
- `list_by_user(user_id)`：查询用户排班结果
- `count_all()`：统计排班结果总数
- `count_by_user(user_id)`：统计用户排班结果数

## 4. 事务与并发
- 名额锁定使用 `BEGIN IMMEDIATE` 事务
- `lock_slot` 会先检查容量，再执行原子更新
- 排班结果写入前会先清空该活动旧结果，保证幂等重跑

## 5. 字段和枚举约定
- Role：`super_admin` / `organizer` / `user`
- ActivityStatus：`draft` / `open` / `closed` / `archived`
- SignupMode：`realtime` / `blind`
- AllocationMode：`greedy` / `first_come` / `lottery`
- RegistrationStatus：`pending` / `confirmed` / `assigned` / `cancelled`

## 6. 维护注意事项
- 任何新增字段都应同步更新 `init_db()` 中的建表 SQL
- 如果要升级数据库结构，优先使用兼容性迁移，不要直接删表
- 当前仓储默认返回 dict，后续如改成 ORM，需要保持上层接口不变
