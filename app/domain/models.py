from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class UserStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ORGANIZER = "organizer"
    USER = "user"


class ActivityStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class SignupMode(str, Enum):
    REALTIME = "realtime"
    BLIND = "blind"


class AllocationMode(str, Enum):
    GREEDY = "greedy"
    FIRST_COME = "first_come"
    LOTTERY = "lottery"
    POINTS = "points"  # 意愿点模式：用户分配 99 意愿点到志愿，高者优先，同级别抽签


# 意愿点模式每用户每活动的总点数上限
MAX_POINTS = 99


class CheckInMode(str, Enum):
    MANUAL = "manual"
    QRCODE = "qrcode"
    SELF_CODE = "self_code"
    LOCATION = "location"
    PHOTO = "photo"


class NotificationMode(str, Enum):
    """用户通知偏好：决定提醒推送渠道"""
    IN_APP = "in_app"  # 应用内通知（弹窗/系统托盘）
    EMAIL = "email"    # 邮件通知（预留，当前仅记录偏好）
    NONE = "none"      # 不提醒


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"
    NOT_ASSIGNED = "not_assigned"


class CheckInStatus(str, Enum):
    CHECKED_IN = "checked_in"
    ABSENT = "absent"


class GroupRole(str, Enum):
    """小组内角色"""
    ADMIN = "admin"   # 小组管理员（创建者）
    MEMBER = "member"  # 普通成员


class MemberStatus(str, Enum):
    """小组成员状态"""
    PENDING = "pending"    # 待审批
    APPROVED = "approved"  # 已通过
    REJECTED = "rejected"  # 已拒绝


class ActivityType(str, Enum):
    """活动模式：归并为两种核心模式"""
    TIME_SLOT = "time_slot"  # 时段模式（活动报名）：按时段报名，可细化岗位
    NON_TIME_SLOT = "non_time_slot"  # 非时段模式（选课/选题等）：按选项报名


class SlotType(str, Enum):
    """报名选项的类型：对应不同的ActivityType"""
    TIME_SLOT = "time_slot"  # 时段（原TimeSlot，默认）
    TOPIC = "topic"  # 选题
    COURSE = "course"  # 课程
    SEAT = "seat"  # 座位
    CUSTOM_OPTION = "custom_option"  # 自定义选项


@dataclass(frozen=True)
class User:
    id: str
    username: str
    role: Role
    status: UserStatus = UserStatus.APPROVED
    avatar_path: str = ""
    notification_mode: NotificationMode = NotificationMode.IN_APP

    @staticmethod
    def create(username: str, role: Role, status: UserStatus = UserStatus.APPROVED) -> "User":
        return User(id=str(uuid4()), username=username, role=role, status=status)


@dataclass(frozen=True)
class Activity:
    id: str
    name: str
    status: ActivityStatus
    owner_id: str
    signup_start: datetime
    signup_end: datetime
    details: str
    signup_mode: SignupMode
    allocation_mode: AllocationMode
    location: str
    activity_type: ActivityType = ActivityType.TIME_SLOT  # 新增：活动类型，默认是排班
    checkin_code: str = ""
    checkin_mode: CheckInMode = CheckInMode.MANUAL
    checkin_start: datetime | None = None
    checkin_end: datetime | None = None
    group_id: str | None = None  # 小组限制：None=公开，非None=仅小组成员可报名
    checkin_closed: bool = False  # 人工提前结束签到（与 checkin_end 时间独立，可逆）
    allow_multiple_slots: bool = False  # 是否允许同一用户兼报多个时段/岗位

    @staticmethod
    def create(
        name: str,
        owner_id: str,
        signup_start: datetime,
        signup_end: datetime,
        details: str,
        signup_mode: SignupMode = SignupMode.REALTIME,
        allocation_mode: AllocationMode = AllocationMode.GREEDY,
        location: str = "",
        activity_type: ActivityType = ActivityType.TIME_SLOT,
        checkin_code: str = "",
        checkin_mode: CheckInMode = CheckInMode.MANUAL,
        checkin_start: datetime | None = None,
        checkin_end: datetime | None = None,
        group_id: str | None = None,
        checkin_closed: bool = False,
        allow_multiple_slots: bool = False,
    ) -> "Activity":
        return Activity(
            id=str(uuid4()),
            name=name,
            status=ActivityStatus.DRAFT,
            owner_id=owner_id,
            signup_start=signup_start,
            signup_end=signup_end,
            details=details,
            signup_mode=signup_mode,
            allocation_mode=allocation_mode,
            location=location,
            activity_type=activity_type,
            checkin_code=checkin_code,
            checkin_mode=checkin_mode,
            checkin_start=checkin_start,
            checkin_end=checkin_end,
            group_id=group_id,
            checkin_closed=checkin_closed,
            allow_multiple_slots=allow_multiple_slots,
        )


@dataclass(frozen=True)
class TimeSlot:
    """通用的报名选项模型：支持时段、选题、课程等多种类型，支持岗位层级"""
    id: str
    activity_id: str
    slot_type: SlotType  # 报名选项类型
    # 通用字段
    name: str  # 选项名称（如"周二下午3-6点"、"机器学习选题A"）
    capacity: int
    used_count: int
    # 时段特有字段
    start_time: datetime | None = None
    end_time: datetime | None = None
    # 岗位层级：parent_slot_id 非空时表示该选项是某时段下的子岗位
    parent_slot_id: str | None = None
    # 拓展字段：用于存储其他类型的特定信息（JSON格式字符串）
    metadata: str = ""  # 存储选题描述、课程信息、座位号等

    @staticmethod
    def create_time_slot(activity_id: str, start_time: datetime, end_time: datetime, capacity: int, name: str = "") -> "TimeSlot":
        """创建时段类型的报名选项（原TimeSlot.create）"""
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.TIME_SLOT,
            name=name or f"{start_time.strftime('%m-%d %H:%M')}~{end_time.strftime('%H:%M')}",
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
            used_count=0,
            parent_slot_id=None,
            metadata="",
        )

    @staticmethod
    def create(activity_id: str, start_time: datetime, end_time: datetime, capacity: int) -> "TimeSlot":
        """保持向后兼容的别名方法：创建时段类型的报名选项"""
        return TimeSlot.create_time_slot(activity_id, start_time, end_time, capacity)

    @staticmethod
    def create_topic(activity_id: str, name: str, capacity: int, description: str = "") -> "TimeSlot":
        """创建选题类型的报名选项"""
        import json
        metadata = json.dumps({"description": description})
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.TOPIC,
            name=name,
            capacity=capacity,
            used_count=0,
            parent_slot_id=None,
            metadata=metadata,
        )

    @staticmethod
    def create_course(activity_id: str, name: str, capacity: int, course_info: dict = None) -> "TimeSlot":
        """创建课程类型的报名选项"""
        import json
        metadata = json.dumps(course_info or {})
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.COURSE,
            name=name,
            capacity=capacity,
            used_count=0,
            parent_slot_id=None,
            metadata=metadata,
        )

    @staticmethod
    def create_seat(activity_id: str, name: str, capacity: int, description: str = "") -> "TimeSlot":
        """创建座位类型的报名选项"""
        import json
        metadata = json.dumps({"description": description})
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.SEAT,
            name=name,
            capacity=capacity,
            used_count=0,
            parent_slot_id=None,
            metadata=metadata,
        )

    @staticmethod
    def create_custom_option(activity_id: str, name: str, capacity: int, description: str = "") -> "TimeSlot":
        """创建自定义类型的报名选项"""
        import json
        metadata = json.dumps({"description": description})
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.CUSTOM_OPTION,
            name=name,
            capacity=capacity,
            used_count=0,
            parent_slot_id=None,
            metadata=metadata,
        )

    @staticmethod
    def create_position(activity_id: str, parent_slot_id: str, name: str, capacity: int) -> "TimeSlot":
        """创建时段下的子岗位（如：接待员、引导员等）"""
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            slot_type=SlotType.TIME_SLOT,
            name=name,
            capacity=capacity,
            used_count=0,
            parent_slot_id=parent_slot_id,
            metadata="",
        )


@dataclass(frozen=True)
class Registration:
    id: str
    user_id: str
    activity_id: str
    slot_id: str
    priority: int
    status: RegistrationStatus
    created_at: datetime
    points: int = 0  # 意愿点模式下用户分配到该志愿的点数（0~MAX_POINTS）

    @staticmethod
    def create(user_id: str, activity_id: str, slot_id: str, priority: int, points: int = 0) -> "Registration":
        return Registration(
            id=str(uuid4()),
            user_id=user_id,
            activity_id=activity_id,
            slot_id=slot_id,
            priority=priority,
            status=RegistrationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            points=points,
        )


@dataclass(frozen=True)
class ScheduleResult:
    id: str
    activity_id: str
    user_id: str
    slot_id: str
    created_at: datetime

    @staticmethod
    def create(activity_id: str, user_id: str, slot_id: str) -> "ScheduleResult":
        return ScheduleResult(
            id=str(uuid4()),
            activity_id=activity_id,
            user_id=user_id,
            slot_id=slot_id,
            created_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class CheckIn:
    id: str
    activity_id: str
    user_id: str
    slot_id: str
    status: CheckInStatus
    checked_at: datetime
    latitude: float | None = None
    longitude: float | None = None
    photo_path: str = ""

    @staticmethod
    def create(
        activity_id: str,
        user_id: str,
        slot_id: str,
        status: CheckInStatus = CheckInStatus.CHECKED_IN,
        latitude: float | None = None,
        longitude: float | None = None,
        photo_path: str = "",
    ) -> "CheckIn":
        return CheckIn(
            id=str(uuid4()),
            activity_id=activity_id,
            user_id=user_id,
            slot_id=slot_id,
            status=status,
            checked_at=datetime.now(timezone.utc),
            latitude=latitude,
            longitude=longitude,
            photo_path=photo_path,
        )


@dataclass(frozen=True)
class Group:
    """用户小组：用于限制活动报名范围"""
    id: str
    name: str
    description: str
    owner_id: str  # 创建者用户ID
    created_at: datetime

    @staticmethod
    def create(name: str, owner_id: str, description: str = "") -> "Group":
        return Group(
            id=str(uuid4()),
            name=name,
            description=description,
            owner_id=owner_id,
            created_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class GroupMember:
    """小组成员记录"""
    group_id: str
    user_id: str
    role: GroupRole
    status: MemberStatus
    joined_at: datetime

    @staticmethod
    def create(
        group_id: str,
        user_id: str,
        role: GroupRole = GroupRole.MEMBER,
        status: MemberStatus = MemberStatus.PENDING,
    ) -> "GroupMember":
        return GroupMember(
            group_id=group_id,
            user_id=user_id,
            role=role,
            status=status,
            joined_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True)
class Notification:
    """系统通知记录：由管理员批量发送或系统自动生成，用户可在通知中心查看。"""
    id: str
    user_id: str           # 接收者
    subject: str           # 标题
    body: str              # 正文
    created_at: datetime
    is_read: bool = False
    sender_id: str = ""    # 发送者用户ID（空白=系统）
    related_link: str = ""  # 可选关联链接（如 activity_id）

    @staticmethod
    def create(
        user_id: str,
        subject: str,
        body: str,
        sender_id: str = "",
        related_link: str = "",
    ) -> "Notification":
        return Notification(
            id=str(uuid4()),
            user_id=user_id,
            subject=subject,
            body=body,
            created_at=datetime.now(timezone.utc),
            is_read=False,
            sender_id=sender_id,
            related_link=related_link,
        )
