"""活动模板数据模型与存储。

模板保存活动的核心配置（不含具体时间），便于快速创建同类活动。
支持周期模式：一次性(once)、每周(weekly)、每月(monthly)、整学期(semester)。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

from app.config import DATA_DIR


class RecurrencePattern(str, Enum):
    """活动周期模式"""
    ONCE = "once"           # 一次性活动
    WEEKLY = "weekly"       # 每周统一报名下周
    MONTHLY = "monthly"     # 每月报名下月
    SEMESTER = "semester"   # 整学期一次性报名


@dataclass
class ActivityTemplate:
    """活动模板 — 存储可复用的活动配置。

    不含具体时间，只保存模式和规则。使用时填入时间即可生成活动。
    """
    id: str
    name: str                           # 模板名称
    description: str = ""               # 模板描述
    activity_type: str = "time_slot"    # 活动模式
    signup_mode: str = "realtime"       # 名额显示模式
    allocation_mode: str = "greedy"     # 分配策略
    checkin_mode: str = "manual"        # 签到模式
    allow_multiple_slots: bool = False  # 兼报设置
    # 预定义时段配置（不含具体日期，只有时间和名称）
    slot_templates: list[dict] = field(default_factory=list)
    # 周期模式
    recurrence: str = "once"
    # 元数据
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "activity_type": self.activity_type,
            "signup_mode": self.signup_mode,
            "allocation_mode": self.allocation_mode,
            "checkin_mode": self.checkin_mode,
            "allow_multiple_slots": self.allow_multiple_slots,
            "slot_templates": self.slot_templates,
            "recurrence": self.recurrence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict) -> "ActivityTemplate":
        return ActivityTemplate(
            id=data.get("id", str(uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            activity_type=data.get("activity_type", "time_slot"),
            signup_mode=data.get("signup_mode", "realtime"),
            allocation_mode=data.get("allocation_mode", "greedy"),
            checkin_mode=data.get("checkin_mode", "manual"),
            allow_multiple_slots=bool(data.get("allow_multiple_slots", False)),
            slot_templates=data.get("slot_templates", []),
            recurrence=data.get("recurrence", "once"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


# ── 模板存储（JSON 文件） ─────────────────────────────────────

def _templates_dir() -> Path:
    p = DATA_DIR / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _templates_file() -> Path:
    return _templates_dir() / "templates.json"


def load_templates() -> list[ActivityTemplate]:
    """从 JSON 文件加载所有模板。"""
    path = _templates_file()
    if not path.exists():
        return _default_templates()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [ActivityTemplate.from_dict(item) for item in data]
    except (json.JSONDecodeError, KeyError):
        return _default_templates()


def save_templates(templates: list[ActivityTemplate]) -> None:
    """保存模板列表到 JSON 文件。"""
    path = _templates_file()
    data = [t.to_dict() for t in templates]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_templates() -> list[ActivityTemplate]:
    """内置默认模板。"""
    now = datetime.now().isoformat()
    return [
        ActivityTemplate(
            id="tpl_weekly_volunteer",
            name="每周志愿服务",
            description="每周统一报名，适用于图书馆、食堂等固定岗位",
            activity_type="time_slot",
            signup_mode="realtime",
            allocation_mode="greedy",
            checkin_mode="qrcode",
            allow_multiple_slots=False,
            recurrence="weekly",
            slot_templates=[
                {"name": "周一上午", "hour_start": 8, "hour_end": 12, "capacity": 5},
                {"name": "周一下午", "hour_start": 14, "hour_end": 17, "capacity": 5},
                {"name": "周二上午", "hour_start": 8, "hour_end": 12, "capacity": 5},
                {"name": "周二下午", "hour_start": 14, "hour_end": 17, "capacity": 5},
            ],
            created_at=now,
            updated_at=now,
        ),
        ActivityTemplate(
            id="tpl_monthly_duty",
            name="每月值班安排",
            description="每月报名下月值班，适用于行政、实验室等按月轮岗场景",
            activity_type="time_slot",
            signup_mode="blind",
            allocation_mode="greedy",
            checkin_mode="manual",
            allow_multiple_slots=False,
            recurrence="monthly",
            slot_templates=[
                {"name": "工作日值班", "hour_start": 9, "hour_end": 18, "capacity": 2},
            ],
            created_at=now,
            updated_at=now,
        ),
        ActivityTemplate(
            id="tpl_semester_course",
            name="学期选课",
            description="整学期一次性选课，适用于课程、选题等场景",
            activity_type="non_time_slot",
            signup_mode="realtime",
            allocation_mode="points",
            checkin_mode="manual",
            allow_multiple_slots=True,
            recurrence="semester",
            slot_templates=[
                {"name": "选题 A", "capacity": 30},
                {"name": "选题 B", "capacity": 30},
                {"name": "选题 C", "capacity": 30},
            ],
            created_at=now,
            updated_at=now,
        ),
        ActivityTemplate(
            id="tpl_one_time_event",
            name="单次活动",
            description="一次性活动，适用于讲座、培训、比赛等场景",
            activity_type="time_slot",
            signup_mode="realtime",
            allocation_mode="first_come",
            checkin_mode="qrcode",
            allow_multiple_slots=False,
            recurrence="once",
            slot_templates=[
                {"name": "上午场", "hour_start": 9, "hour_end": 12, "capacity": 50},
                {"name": "下午场", "hour_start": 14, "hour_end": 17, "capacity": 50},
            ],
            created_at=now,
            updated_at=now,
        ),
    ]
