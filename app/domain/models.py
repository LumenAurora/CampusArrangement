from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ORGANIZER = "organizer"
    USER = "user"


class ActivityStatus(str, Enum):
    DRAFT = "draft"
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


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class User:
    id: str
    username: str
    role: Role

    @staticmethod
    def create(username: str, role: Role) -> "User":
        return User(id=str(uuid4()), username=username, role=role)


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

    @staticmethod
    def create(
        name: str,
        owner_id: str,
        signup_start: datetime,
        signup_end: datetime,
        details: str,
        signup_mode: SignupMode = SignupMode.REALTIME,
        allocation_mode: AllocationMode = AllocationMode.GREEDY,
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
        )


@dataclass(frozen=True)
class TimeSlot:
    id: str
    activity_id: str
    start_time: datetime
    end_time: datetime
    capacity: int
    used_count: int

    @staticmethod
    def create(activity_id: str, start_time: datetime, end_time: datetime, capacity: int) -> "TimeSlot":
        return TimeSlot(
            id=str(uuid4()),
            activity_id=activity_id,
            start_time=start_time,
            end_time=end_time,
            capacity=capacity,
            used_count=0,
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

    @staticmethod
    def create(user_id: str, activity_id: str, slot_id: str, priority: int) -> "Registration":
        return Registration(
            id=str(uuid4()),
            user_id=user_id,
            activity_id=activity_id,
            slot_id=slot_id,
            priority=priority,
            status=RegistrationStatus.PENDING,
            created_at=datetime.now(timezone.utc),
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
