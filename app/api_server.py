from __future__ import annotations

import logging
import secrets
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.exceptions import CapacityExceeded, ConflictError, PermissionDenied, ValidationError
from app.domain.models import MAX_POINTS, ActivityStatus, ActivityType, AllocationMode, CheckInMode, CheckInStatus, NotificationMode, RegistrationStatus, Role, SignupMode, SlotType, User, UserStatus
from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
    GroupRepository,
    NotificationRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Campus Scheduler API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
user_repo = UserRepository()
activity_repo = ActivityRepository()
slot_repo = TimeSlotRepository()
reg_repo = RegistrationRepository()
schedule_repo = ScheduleRepository()
checkin_repo = CheckInRepository()
group_repo = GroupRepository()
notification_repo = NotificationRepository()

user_service = UserService(user_repo)
activity_service = ActivityService(activity_repo, slot_repo)
registration_service = RegistrationService(slot_repo, reg_repo, activity_repo, group_repo, notification_repo)
scheduling_service = SchedulingService(reg_repo, slot_repo, schedule_repo, activity_repo, notification_repo)
checkin_service = CheckInService(checkin_repo, schedule_repo, activity_repo)

_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()
_TOKEN_TTL = 86400


def _ensure_admin() -> None:
    if user_repo.get_by_username("admin"):
        return
    user_service.register(current_user=None, username="admin", password="admin", role=Role.SUPER_ADMIN)


_ensure_admin()


def _cleanup_tokens() -> None:
    now = time.time()
    with _tokens_lock:
        expired = [t for t, (_, ts) in _tokens.items() if now - ts > _TOKEN_TTL]
        for t in expired:
            del _tokens[t]


class LoginRequest(BaseModel):
    username: str
    password: str


class ActivityCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    signup_start: datetime
    signup_end: datetime
    details: str
    signup_mode: SignupMode = SignupMode.REALTIME
    allocation_mode: AllocationMode = AllocationMode.GREEDY
    location: str = ""
    activity_type: ActivityType = ActivityType.TIME_SLOT
    checkin_mode: CheckInMode = CheckInMode.MANUAL
    checkin_start: datetime | None = None
    checkin_end: datetime | None = None
    group_id: str | None = None
    allow_multiple_slots: bool = False


class ActivityUpdateRequest(BaseModel):
    name: str | None = None
    signup_start: datetime | None = None
    signup_end: datetime | None = None
    details: str | None = None
    location: str | None = None


class SlotCreateRequest(BaseModel):
    start_time: datetime | None = None
    end_time: datetime | None = None
    capacity: int = Field(..., ge=1)
    slot_type: str = "time_slot"
    name: str = ""
    metadata: str = ""
    parent_slot_id: str | None = None  # 子岗位的父时段ID


class PositionCreateRequest(BaseModel):
    parent_slot_id: str
    name: str = Field(..., min_length=1)
    capacity: int = Field(..., ge=1)


class RegistrationRequest(BaseModel):
    activity_id: str
    slot_id: str
    priority: int = Field(..., ge=1)
    points: int = Field(0, ge=0, le=99)  # 意愿点模式：用户对该志愿分配的点数


class ScheduleRunRequest(BaseModel):
    activity_id: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Role


class SelfRegisterRequest(BaseModel):
    username: str
    password: str


class CheckInRequest(BaseModel):
    activity_id: str
    user_id: str
    slot_id: str


class StatusUpdateRequest(BaseModel):
    action: str = Field(..., pattern="^(publish|close|archive|submit_review|reject|reopen)$")


class DuplicateActivityRequest(BaseModel):
    new_signup_start: datetime
    new_signup_end: datetime
    new_checkin_start: datetime | None = None
    new_checkin_end: datetime | None = None


class SelfCheckInRequest(BaseModel):
    activity_id: str
    slot_id: str
    checkin_code: str


class LocationCheckInRequest(BaseModel):
    activity_id: str
    slot_id: str
    latitude: float
    longitude: float


class PhotoCheckInRequest(BaseModel):
    activity_id: str
    slot_id: str
    photo_path: str


class UnmarkAbsentRequest(BaseModel):
    activity_id: str
    user_id: str
    slot_id: str


def _to_user(record: dict) -> User:
    return User(id=record["id"], username=record["username"], role=Role(record["role"]),
                status=UserStatus(record.get("status", "approved")),
                avatar_path=record.get("avatar_path", ""),
                notification_mode=NotificationMode(record.get("notification_mode", "in_app")))


def _strip_secrets(record: dict | None) -> dict:
    """剔除用户记录中的敏感字段（如 password_hash），返回可安全返回给前端的 dict。"""
    if not record:
        return {}
    return {k: v for k, v in record.items() if k != "password_hash"}


def _get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="认证信息无效")
    token = parts[1].strip()
    _cleanup_tokens()
    with _tokens_lock:
        entry = _tokens.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="登录已失效")
    user_id, created_at = entry
    if time.time() - created_at > _TOKEN_TTL:
        with _tokens_lock:
            _tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="登录已过期")
    record = user_repo.get_by_id(user_id)
    if not record:
        raise HTTPException(status_code=401, detail="用户不存在")
    user = _to_user(record)
    # 校验用户当前状态：REJECTED/PENDING 用户即便持有旧 token 也不允许操作
    if user.status != UserStatus.APPROVED:
        with _tokens_lock:
            _tokens.pop(token, None)
        raise HTTPException(status_code=403, detail="账号已被禁用或尚未审批通过")
    return user


def _require_roles(user: User, roles: set[Role]) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="权限不足")


def _check_activity_access(user: User, activity_id: str) -> dict:
    """校验用户对活动的访问权限：超级管理员或活动 owner 可访问，
    否则抛 403。返回活动记录供后续使用。"""
    activity = activity_repo.get(activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    if user.role != Role.SUPER_ADMIN and activity.get("owner_id") != user.id:
        raise HTTPException(status_code=403, detail="无权访问该活动的数据")
    return activity


def _filter_records_by_activity_access(user: User, records: list[dict]) -> list[dict]:
    """Filter user-scoped records so organizers only see records for owned activities."""
    if user.role == Role.SUPER_ADMIN:
        return records
    if user.role != Role.ORGANIZER:
        return records
    visible: list[dict] = []
    for record in records:
        activity = activity_repo.get(str(record.get("activity_id", "")))
        if activity and activity.get("owner_id") == user.id:
            visible.append(record)
    return visible


def _handle_domain_error(exc: Exception) -> None:
    if isinstance(exc, PermissionDenied):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, (ValidationError, CapacityExceeded)):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/auth/login")
def login(payload: LoginRequest) -> dict:
    try:
        user = user_service.authenticate(payload.username, payload.password)
    except Exception as exc:
        _handle_domain_error(exc)
    token = secrets.token_hex(16)
    with _tokens_lock:
        _tokens[token] = (user.id, time.time())
    # 读取完整用户记录以返回头像与通知偏好
    record = user_repo.get_by_id(user.id) or {}
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role.value,
            "status": user.status.value,
            "avatar_path": record.get("avatar_path", ""),
            "notification_mode": record.get("notification_mode", "in_app"),
        },
    }


def _strip_secrets(user: dict | None) -> dict | None:
    """剔除用户记录中的敏感字段（password_hash），避免通过 API 外泄。"""
    if user is None:
        return None
    return {k: v for k, v in user.items() if k != "password_hash"}


@app.get("/users")
def list_users(
    username: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    if username:
        user = user_repo.get_by_username(username)
        stripped = _strip_secrets(user)
        return [stripped] if stripped else []
    return [_strip_secrets(user) for user in user_repo.list_all()]


@app.get("/users/pending")
def list_pending_users(current_user: User = Depends(_get_current_user)) -> list[dict]:
    """获取待审批用户列表"""
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        return user_service.list_pending_users(current_user)
    except Exception as exc:
        _handle_domain_error(exc)


@app.get("/users/{user_id}")
def get_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    if user_id == "me":
        record = user_repo.get_by_id(current_user.id)
        stripped = _strip_secrets(record)
        if not stripped:
            raise HTTPException(status_code=404, detail="用户不存在")
        return stripped
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    user = user_repo.get_by_id(user_id)
    stripped = _strip_secrets(user)
    if not stripped:
        raise HTTPException(status_code=404, detail="用户不存在")
    return stripped


@app.post("/users")
def create_user(payload: UserCreateRequest, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        user = user_service.register(current_user=current_user, username=payload.username, password=payload.password, role=payload.role)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"id": user.id, "username": user.username, "role": user.role.value, "status": user.status.value}


@app.post("/users/{user_id}/delete")
def delete_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user_service.delete_user(current_user, user_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/auth/register")
def self_register(payload: SelfRegisterRequest) -> dict:
    """用户自助注册，注册后需等待审批"""
    try:
        user = user_service.self_register(username=payload.username, password=payload.password)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"id": user.id, "username": user.username, "role": user.role.value, "status": user.status.value}


@app.post("/users/{user_id}/approve")
def approve_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    """审批通过用户注册"""
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user = user_service.approve_user(current_user, user_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"id": user.id, "username": user.username, "role": user.role.value, "status": user.status.value}


@app.post("/users/{user_id}/reject")
def reject_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    """拒绝用户注册"""
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user_service.reject_user(current_user, user_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


# 头像存储目录
_AVATAR_DIR = Path(__file__).resolve().parent.parent / "resources" / "uploads" / "avatars"
_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
_ALLOWED_AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2MB


@app.get("/users/me")
def get_me(current_user: User = Depends(_get_current_user)) -> dict:
    """获取当前登录用户的完整信息（含头像与通知偏好）。"""
    record = user_repo.get_by_id(current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="用户不存在")
    return _strip_secrets(record)


class SettingsUpdateRequest(BaseModel):
    notification_mode: NotificationMode = NotificationMode.IN_APP


@app.put("/users/me/settings")
def update_my_settings(payload: SettingsUpdateRequest, current_user: User = Depends(_get_current_user)) -> dict:
    """更新当前用户的通知偏好。"""
    try:
        user_repo.update_notification_mode(current_user.id, payload.notification_mode.value)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True, "notification_mode": payload.notification_mode.value}


@app.get("/notifications")
def list_my_notifications(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    """分页获取当前用户的站内通知。"""
    return notification_repo.list_by_user(current_user.id, limit=max(1, min(limit, 100)), offset=max(0, offset))


@app.get("/notifications/unread-count")
def count_my_unread_notifications(current_user: User = Depends(_get_current_user)) -> dict:
    """获取当前用户未读通知数。"""
    return {"count": notification_repo.count_unread(current_user.id)}


@app.post("/notifications/{notification_id}/read")
def mark_my_notification_read(
    notification_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    """标记当前用户的一条通知为已读。"""
    notification = notification_repo.get(notification_id)
    if not notification or notification.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification_repo.mark_as_read(notification_id)
    return {"ok": True}


@app.post("/notifications/read-all")
def mark_all_my_notifications_read(current_user: User = Depends(_get_current_user)) -> dict:
    """标记当前用户全部通知为已读。"""
    notification_repo.mark_all_as_read(current_user.id)
    return {"ok": True}


@app.delete("/notifications/read")
def delete_my_read_notifications(current_user: User = Depends(_get_current_user)) -> dict:
    """删除当前用户全部已读通知。"""
    return {"count": notification_repo.delete_read_by_user(current_user.id)}


@app.post("/users/me/avatar")
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(_get_current_user),
) -> dict:
    """上传当前用户头像。保存到 resources/uploads/avatars/{user_id}.{ext}。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_AVATAR_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的头像格式，仅支持 {', '.join(_ALLOWED_AVATAR_EXTS)}")
    content = await file.read()
    if len(content) > _MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail=f"头像大小不能超过 {_MAX_AVATAR_BYTES // 1024}KB")
    save_path = _AVATAR_DIR / f"{current_user.id}{ext}"
    save_path.write_bytes(content)
    # 存相对路径，便于本地/远程统一
    rel_path = f"avatars/{current_user.id}{ext}"
    try:
        user_repo.update_avatar(current_user.id, rel_path)
    except Exception as exc:
        # 写库失败时清理已写入的孤儿文件，避免磁盘残留与 DB 不一致
        try:
            save_path.unlink(missing_ok=True)
        except OSError:
            pass
        _handle_domain_error(exc)
    # 清理同 user_id 的旧扩展名文件（用户可能从 .png 切换到 .jpg）
    for old in _AVATAR_DIR.glob(f"{current_user.id}.*"):
        if old != save_path:
            try:
                old.unlink(missing_ok=True)
            except OSError:
                pass
    return {"ok": True, "avatar_path": rel_path}


@app.post("/checkin/{activity_id}/close")
def close_checkin(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    """人工提前结束签到。"""
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin_service.close_checkin(current_user, activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/checkin/{activity_id}/reopen")
def reopen_checkin(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    """恢复签到（撤销人工提前结束）。"""
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin_service.reopen_checkin(current_user, activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


def _filter_visible_activities_for_user(user: User, activities: list[dict]) -> list[dict]:
    if user.role in {Role.SUPER_ADMIN, Role.ORGANIZER}:
        return activities
    visible_statuses = {
        ActivityStatus.OPEN.value,
        ActivityStatus.CLOSED.value,
        ActivityStatus.ARCHIVED.value,
    }
    return [activity for activity in activities if activity.get("status") in visible_statuses]


def _is_activity_visible_to_user(user: User, activity: dict) -> bool:
    return bool(_filter_visible_activities_for_user(user, [activity]))


def _ensure_slot_visible_to_user(user: User, slot_id: str) -> dict:
    slot = slot_repo.get(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="时段不存在")
    activity = activity_repo.get(slot.get("activity_id", ""))
    if not activity or not _is_activity_visible_to_user(user, activity):
        raise HTTPException(status_code=404, detail="时段不存在")
    return slot


@app.get("/activities")
def list_activities(status: Optional[str] = None, current_user: User = Depends(_get_current_user)) -> list[dict]:
    if status:
        valid_statuses = {s.value for s in ActivityStatus}
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"无效的活动状态: {status}")
        return _filter_visible_activities_for_user(current_user, activity_repo.list_by_status(ActivityStatus(status)))
    return _filter_visible_activities_for_user(current_user, activity_service.list_activities())


@app.get("/activities/{activity_id}")
def get_activity(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    activity = activity_repo.get(activity_id)
    if not activity or not _is_activity_visible_to_user(current_user, activity):
        raise HTTPException(status_code=404, detail="活动不存在")
    return activity


@app.post("/activities")
def create_activity(payload: ActivityCreateRequest, current_user: User = Depends(_get_current_user)) -> dict:
    try:
        activity = activity_service.create_activity(
            user=current_user,
            name=payload.name,
            signup_start=payload.signup_start,
            signup_end=payload.signup_end,
            details=payload.details,
            signup_mode=payload.signup_mode,
            allocation_mode=payload.allocation_mode,
            location=payload.location,
            activity_type=payload.activity_type,
            checkin_mode=payload.checkin_mode.value,
            checkin_start=payload.checkin_start,
            checkin_end=payload.checkin_end,
            group_id=payload.group_id,
            allow_multiple_slots=payload.allow_multiple_slots,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": activity.id,
        "name": activity.name,
        "status": activity.status.value,
        "owner_id": activity.owner_id,
        "signup_start": activity.signup_start.isoformat(),
        "signup_end": activity.signup_end.isoformat(),
        "details": activity.details,
        "signup_mode": activity.signup_mode.value,
        "allocation_mode": activity.allocation_mode.value,
        "location": activity.location,
        "activity_type": activity.activity_type.value,
        "checkin_code": activity.checkin_code,
        "checkin_mode": activity.checkin_mode.value,
        "checkin_start": activity.checkin_start.isoformat() if activity.checkin_start else None,
        "checkin_end": activity.checkin_end.isoformat() if activity.checkin_end else None,
        "group_id": activity.group_id,
        "allow_multiple_slots": activity.allow_multiple_slots,
    }


@app.post("/activities/{activity_id}/delete")
def delete_activity(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    try:
        activity_service.delete_activity(user=current_user, activity_id=activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.put("/activities/{activity_id}")
def update_activity(
    activity_id: str,
    payload: ActivityUpdateRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    for key in ("signup_start", "signup_end"):
        if key in fields and fields[key] is not None:
            fields[key] = fields[key].isoformat()
    try:
        activity_service.update_activity(user=current_user, activity_id=activity_id, fields=fields)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/activities/{activity_id}/duplicate")
def duplicate_activity(
    activity_id: str,
    payload: DuplicateActivityRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        activity = activity_service.duplicate_activity(
            user=current_user,
            activity_id=activity_id,
            new_signup_start=payload.new_signup_start,
            new_signup_end=payload.new_signup_end,
            new_checkin_start=payload.new_checkin_start,
            new_checkin_end=payload.new_checkin_end,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": activity.id,
        "name": activity.name,
        "status": activity.status.value,
        "owner_id": activity.owner_id,
        "signup_start": activity.signup_start.isoformat(),
        "signup_end": activity.signup_end.isoformat(),
        "details": activity.details,
        "signup_mode": activity.signup_mode.value,
        "allocation_mode": activity.allocation_mode.value,
        "location": activity.location,
        "activity_type": activity.activity_type.value,
        "checkin_code": activity.checkin_code,
        "checkin_mode": activity.checkin_mode.value,
        "checkin_start": activity.checkin_start.isoformat() if activity.checkin_start else None,
        "checkin_end": activity.checkin_end.isoformat() if activity.checkin_end else None,
        "group_id": activity.group_id,
        "allow_multiple_slots": activity.allow_multiple_slots,
    }


@app.post("/activities/{activity_id}/status")
def update_activity_status(
    activity_id: str,
    payload: StatusUpdateRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        if payload.action == "publish":
            activity_service.publish_activity(user=current_user, activity_id=activity_id)
        elif payload.action == "close":
            activity_service.close_activity(user=current_user, activity_id=activity_id)
            # Auto-schedule after closing; rollback to OPEN on failure
            try:
                scheduling_service.run(activity_id)
            except Exception as e:
                logger.warning(f"Auto-scheduling failed for activity {activity_id}: {e}")
                try:
                    activity_service.reopen_activity(user=current_user, activity_id=activity_id)
                except Exception:
                    pass
                raise ValidationError(f"排班失败，活动已重新开放：{e}") from e
        elif payload.action == "reopen":
            activity_service.reopen_activity(user=current_user, activity_id=activity_id)
        elif payload.action == "archive":
            activity_service.archive_activity(user=current_user, activity_id=activity_id)
        elif payload.action == "submit_review":
            activity_service.submit_for_review(user=current_user, activity_id=activity_id)
        elif payload.action == "reject":
            activity_service.reject_activity(user=current_user, activity_id=activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.get("/activities/{activity_id}/slots")
def list_slots(activity_id: str, current_user: User = Depends(_get_current_user)) -> list[dict]:
    activity = activity_repo.get(activity_id)
    if not activity or not _is_activity_visible_to_user(current_user, activity):
        raise HTTPException(status_code=404, detail="活动不存在")
    return slot_repo.list_by_activity(activity_id)


@app.get("/activities/{activity_id}/slots/{parent_slot_id}/positions")
def list_positions(
    activity_id: str,
    parent_slot_id: str,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    """获取某时段下的所有子岗位"""
    activity = activity_repo.get(activity_id)
    if not activity or not _is_activity_visible_to_user(current_user, activity):
        raise HTTPException(status_code=404, detail="活动不存在")
    _ensure_slot_visible_to_user(current_user, parent_slot_id)
    return slot_repo.list_positions(parent_slot_id)


@app.get("/slots/{parent_slot_id}/positions")
def list_positions_by_parent(parent_slot_id: str, current_user: User = Depends(_get_current_user)) -> list[dict]:
    """获取某时段下的所有子岗位（无需活动ID的兼容入口）。"""
    _ensure_slot_visible_to_user(current_user, parent_slot_id)
    return slot_repo.list_positions(parent_slot_id)


@app.post("/activities/{activity_id}/positions")
def add_position(
    activity_id: str,
    payload: PositionCreateRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        slot = activity_service.add_position(
            user=current_user,
            activity_id=activity_id,
            parent_slot_id=payload.parent_slot_id,
            name=payload.name,
            capacity=payload.capacity,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": slot.id,
        "activity_id": slot.activity_id,
        "slot_type": slot.slot_type.value,
        "name": slot.name,
        "start_time": slot.start_time.isoformat() if slot.start_time else None,
        "end_time": slot.end_time.isoformat() if slot.end_time else None,
        "capacity": slot.capacity,
        "used_count": slot.used_count,
        "parent_slot_id": slot.parent_slot_id,
        "metadata": slot.metadata,
    }


@app.get("/slots/{slot_id}")
def get_slot(slot_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    return _ensure_slot_visible_to_user(current_user, slot_id)


@app.post("/activities/{activity_id}/slots")
def add_slot(
    activity_id: str,
    payload: SlotCreateRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        # 如果有 parent_slot_id，添加子岗位
        if payload.parent_slot_id:
            slot = activity_service.add_position(
                user=current_user,
                activity_id=activity_id,
                parent_slot_id=payload.parent_slot_id,
                name=payload.name,
                capacity=payload.capacity,
            )
        else:
            slot_type = SlotType(payload.slot_type)
            if slot_type == SlotType.TIME_SLOT:
                if not payload.start_time or not payload.end_time:
                    raise ValidationError("时段类型必须设置开始和结束时间")
                slot = activity_service.add_slot(
                    user=current_user,
                    activity_id=activity_id,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                    capacity=payload.capacity,
                    name=payload.name,
                )
            else:
                slot = activity_service.add_slot_generic(
                    user=current_user,
                    activity_id=activity_id,
                    slot_type=slot_type,
                    name=payload.name,
                    capacity=payload.capacity,
                    start_time=payload.start_time,
                    end_time=payload.end_time,
                    metadata=payload.metadata,
                )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": slot.id,
        "activity_id": slot.activity_id,
        "slot_type": slot.slot_type.value,
        "name": slot.name,
        "start_time": slot.start_time.isoformat() if slot.start_time else None,
        "end_time": slot.end_time.isoformat() if slot.end_time else None,
        "capacity": slot.capacity,
        "used_count": slot.used_count,
        "parent_slot_id": slot.parent_slot_id,
        "metadata": slot.metadata,
    }


@app.get("/registrations")
def list_registrations(
    user_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        _check_activity_access(current_user, activity_id)
        if status == "pending":
            return reg_repo.list_pending(activity_id)
        all_regs = reg_repo.list_by_activity(activity_id)
        if status:
            # 仅返回符合状态过滤的报名，避免静默忽略 status 参数
            return [r for r in all_regs if r.get("status") == status]
        return all_regs
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return _filter_records_by_activity_access(current_user, reg_repo.list_by_user(user_id))
    return []


@app.get("/registrations/{registration_id}")
def get_registration(registration_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    reg = reg_repo.get(registration_id)
    if not reg:
        raise HTTPException(status_code=404, detail="报名记录不存在")
    if current_user.role in {Role.SUPER_ADMIN, Role.ORGANIZER}:
        _check_activity_access(current_user, reg.get("activity_id", ""))
    elif reg.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="权限不足")
    return reg


@app.post("/registrations")
def create_registration(
    payload: RegistrationRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        registration = registration_service.register(
            user_id=current_user.id,
            activity_id=payload.activity_id,
            slot_id=payload.slot_id,
            priority=payload.priority,
            points=payload.points,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": registration.id,
        "user_id": registration.user_id,
        "activity_id": registration.activity_id,
        "slot_id": registration.slot_id,
        "priority": registration.priority,
        "points": registration.points,
        "status": registration.status.value,
        "created_at": registration.created_at.isoformat(),
    }


@app.post("/registrations/{registration_id}/cancel")
def cancel_registration(
    registration_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        registration_service.cancel(user_id=current_user.id, registration_id=registration_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/scheduling/run")
def run_scheduling(payload: ScheduleRunRequest, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    _check_activity_access(current_user, payload.activity_id)
    try:
        count = scheduling_service.run(payload.activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"count": count}


@app.get("/schedules")
def list_schedules(
    activity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        _check_activity_access(current_user, activity_id)
        return schedule_repo.list_by_activity(activity_id)
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return _filter_records_by_activity_access(current_user, schedule_repo.list_by_user(user_id))
    raise HTTPException(status_code=400, detail="必须提供 activity_id 或 user_id")

@app.get("/checkins")
def list_checkins(
    activity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        _check_activity_access(current_user, activity_id)
        return checkin_repo.list_by_activity(activity_id)
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return _filter_records_by_activity_access(current_user, checkin_repo.list_by_user(user_id))
    return []


@app.get("/checkins/{checkin_id}")
def get_checkin(checkin_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    ci = checkin_repo.get(checkin_id)
    if not ci:
        raise HTTPException(status_code=404, detail="签到记录不存在")
    if current_user.role in {Role.SUPER_ADMIN, Role.ORGANIZER}:
        _check_activity_access(current_user, ci.get("activity_id", ""))
    elif ci.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="权限不足")
    return ci


@app.post("/checkins")
def create_checkin(
    payload: CheckInRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin = checkin_service.check_in(
            user=current_user,
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            slot_id=payload.slot_id,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": checkin.id,
        "activity_id": checkin.activity_id,
        "user_id": checkin.user_id,
        "slot_id": checkin.slot_id,
        "status": checkin.status.value,
        "checked_at": checkin.checked_at.isoformat(),
        "latitude": checkin.latitude,
        "longitude": checkin.longitude,
        "photo_path": checkin.photo_path,
    }


class MarkAbsentRequest(BaseModel):
    activity_id: str
    user_id: str
    slot_id: str


@app.post("/checkins/absent")
def mark_absent(
    payload: MarkAbsentRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin_service.mark_absent(
            user=current_user,
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            slot_id=payload.slot_id,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/checkins/unmark_absent")
def unmark_absent(
    payload: UnmarkAbsentRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin_service.unmark_absent(
            user=current_user,
            activity_id=payload.activity_id,
            user_id=payload.user_id,
            slot_id=payload.slot_id,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {"ok": True}


@app.post("/activities/{activity_id}/generate_checkin_code")
def generate_checkin_code(
    activity_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        code = checkin_service.generate_checkin_code(user=current_user, activity_id=activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
    return {"checkin_code": code}


@app.post("/checkins/self")
def self_check_in(
    payload: SelfCheckInRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        checkin = checkin_service.self_check_in(
            user_id=current_user.id,
            activity_id=payload.activity_id,
            slot_id=payload.slot_id,
            checkin_code=payload.checkin_code,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": checkin.id,
        "activity_id": checkin.activity_id,
        "user_id": checkin.user_id,
        "slot_id": checkin.slot_id,
        "status": checkin.status.value,
        "checked_at": checkin.checked_at.isoformat(),
        "latitude": checkin.latitude,
        "longitude": checkin.longitude,
        "photo_path": checkin.photo_path,
    }


@app.post("/checkins/location")
def location_check_in(
    payload: LocationCheckInRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        checkin = checkin_service.location_check_in(
            user_id=current_user.id,
            activity_id=payload.activity_id,
            slot_id=payload.slot_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": checkin.id,
        "activity_id": checkin.activity_id,
        "user_id": checkin.user_id,
        "slot_id": checkin.slot_id,
        "status": checkin.status.value,
        "checked_at": checkin.checked_at.isoformat(),
        "latitude": checkin.latitude,
        "longitude": checkin.longitude,
        "photo_path": checkin.photo_path,
    }


@app.post("/checkins/photo")
def photo_check_in(
    payload: PhotoCheckInRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        checkin = checkin_service.photo_check_in(
            user_id=current_user.id,
            activity_id=payload.activity_id,
            slot_id=payload.slot_id,
            photo_path=payload.photo_path,
        )
    except Exception as exc:
        _handle_domain_error(exc)
    return {
        "id": checkin.id,
        "activity_id": checkin.activity_id,
        "user_id": checkin.user_id,
        "slot_id": checkin.slot_id,
        "status": checkin.status.value,
        "checked_at": checkin.checked_at.isoformat(),
        "latitude": checkin.latitude,
        "longitude": checkin.longitude,
        "photo_path": checkin.photo_path,
    }


@app.get("/activities/{activity_id}/checkin_stats")
def checkin_stats(
    activity_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    # 允许管理员查看所有活动统计，普通用户查看自己参与的活动
    activity = activity_repo.get(activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="活动不存在")
    if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
        # 普通用户只能查看自己参与的活动的统计
        user_schedules = schedule_repo.list_by_user(current_user.id)
        if not any(s["activity_id"] == activity_id for s in user_schedules):
            raise HTTPException(status_code=403, detail="权限不足")
    try:
        return checkin_service.get_checkin_stats(activity_id)
    except Exception as exc:
        _handle_domain_error(exc)


@app.get("/metrics/overview")
def metrics_overview(_: User = Depends(_get_current_user)) -> dict:
    return {
        "activities": activity_repo.count_all(),
        "slots": slot_repo.count_all(),
        "registrations": reg_repo.count_all(),
        "schedules": schedule_repo.count_all(),
    }


@app.get("/metrics/slots-count")
def metrics_slots_count(status: str, _: User = Depends(_get_current_user)) -> dict:
    return {"count": slot_repo.count_by_activity_status(status)}


@app.get("/metrics/users/{user_id}")
def metrics_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="权限不足")
    return {
        "registrations": reg_repo.count_by_user(user_id),
        "schedules": schedule_repo.count_by_user(user_id),
    }
