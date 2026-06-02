from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.application.activity_service import ActivityService
from app.application.checkin_service import CheckInService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.exceptions import CapacityExceeded, ConflictError, PermissionDenied, ValidationError
from app.domain.models import AllocationMode, CheckInStatus, Role, SignupMode, User
from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    CheckInRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)

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

user_service = UserService(user_repo)
activity_service = ActivityService(activity_repo, slot_repo)
registration_service = RegistrationService(slot_repo, reg_repo, activity_repo)
scheduling_service = SchedulingService(reg_repo, slot_repo, schedule_repo, activity_repo)
checkin_service = CheckInService(checkin_repo, schedule_repo)

_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()
_TOKEN_TTL = 86400


def _ensure_admin() -> None:
    if user_repo.get_by_username("admin"):
        return
    user_service.register(username="admin", password="admin", role=Role.SUPER_ADMIN)


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


class SlotCreateRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int = Field(..., ge=1)


class RegistrationRequest(BaseModel):
    activity_id: str
    slot_id: str
    priority: int = Field(..., ge=1)


class ScheduleRunRequest(BaseModel):
    activity_id: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: Role


class CheckInRequest(BaseModel):
    activity_id: str
    user_id: str
    slot_id: str


class StatusUpdateRequest(BaseModel):
    action: str = Field(..., pattern="^(publish|close|archive)$")


def _to_user(record: dict) -> User:
    return User(id=record["id"], username=record["username"], role=Role(record["role"]))


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
    return _to_user(record)


def _require_roles(user: User, roles: set[Role]) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="权限不足")


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
        raise
    token = secrets.token_hex(16)
    with _tokens_lock:
        _tokens[token] = (user.id, time.time())
    return {
        "token": token,
        "user": {"id": user.id, "username": user.username, "role": user.role.value},
    }


@app.get("/users")
def list_users(current_user: User = Depends(_get_current_user)) -> list[dict]:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    return user_repo.list_all()


@app.post("/users")
def create_user(payload: UserCreateRequest, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user = user_service.register(payload.username, payload.password, payload.role)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"id": user.id, "username": user.username, "role": user.role.value}


@app.post("/users/{user_id}/delete")
def delete_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user_service.delete_user(current_user, user_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"ok": True}


@app.get("/activities")
def list_activities(status: Optional[str] = None, _: User = Depends(_get_current_user)) -> list[dict]:
    if status:
        valid_statuses = {s.value for s in ActivityStatus}
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"无效的活动状态: {status}")
        return activity_repo.list_by_status(ActivityStatus(status))
    return activity_service.list_activities()


@app.get("/activities/{activity_id}")
def get_activity(activity_id: str, _: User = Depends(_get_current_user)) -> dict:
    activity = activity_repo.get(activity_id)
    if not activity:
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
        )
    except Exception as exc:
        _handle_domain_error(exc)
        raise
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
    }


@app.post("/activities/{activity_id}/delete")
def delete_activity(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    try:
        activity_service.delete_activity(user=current_user, activity_id=activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"ok": True}


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
        elif payload.action == "archive":
            activity_service.archive_activity(user=current_user, activity_id=activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"ok": True}


@app.get("/activities/{activity_id}/slots")
def list_slots(activity_id: str, _: User = Depends(_get_current_user)) -> list[dict]:
    return slot_repo.list_by_activity(activity_id)


@app.post("/activities/{activity_id}/slots")
def add_slot(
    activity_id: str,
    payload: SlotCreateRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    try:
        slot = activity_service.add_slot(
            user=current_user,
            activity_id=activity_id,
            start_time=payload.start_time,
            end_time=payload.end_time,
            capacity=payload.capacity,
        )
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {
        "id": slot.id,
        "activity_id": slot.activity_id,
        "start_time": slot.start_time.isoformat(),
        "end_time": slot.end_time.isoformat(),
        "capacity": slot.capacity,
        "used_count": slot.used_count,
    }


@app.get("/registrations")
def list_registrations(
    user_id: Optional[str] = None,
    activity_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise HTTPException(status_code=403, detail="权限不足")
        return reg_repo.list_pending(activity_id)
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return reg_repo.list_by_user(user_id)
    return []


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
        )
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {
        "id": registration.id,
        "user_id": registration.user_id,
        "activity_id": registration.activity_id,
        "slot_id": registration.slot_id,
        "priority": registration.priority,
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
        raise
    return {"ok": True}


@app.post("/scheduling/run")
def run_scheduling(payload: ScheduleRunRequest, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        count = scheduling_service.run(payload.activity_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"count": count}


@app.get("/schedules")
def list_schedules(
    activity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        return schedule_repo.list_by_activity(activity_id)
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return schedule_repo.list_by_user(user_id)
    raise HTTPException(status_code=400, detail="必须提供 activity_id 或 user_id")


@app.get("/checkins")
def list_checkins(
    activity_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(_get_current_user),
) -> list[dict]:
    if activity_id:
        return checkin_repo.list_by_activity(activity_id)
    if user_id:
        if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
            raise HTTPException(status_code=403, detail="权限不足")
        return checkin_repo.list_by_user(user_id)
    return []


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
        raise
    return {
        "id": checkin.id,
        "activity_id": checkin.activity_id,
        "user_id": checkin.user_id,
        "slot_id": checkin.slot_id,
        "status": checkin.status.value,
        "checked_at": checkin.checked_at.isoformat(),
    }


@app.post("/checkins/{checkin_id}/absent")
def mark_absent(
    checkin_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    try:
        checkin_service.mark_absent(user=current_user, checkin_id=checkin_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"ok": True}


@app.get("/metrics/overview")
def metrics_overview(_: User = Depends(_get_current_user)) -> dict:
    return {
        "activities": activity_repo.count_all(),
        "slots": slot_repo.count_all(),
        "registrations": reg_repo.count_all(),
        "schedules": schedule_repo.count_all(),
    }


@app.get("/metrics/users/{user_id}")
def metrics_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    if current_user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER} and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="权限不足")
    return {
        "registrations": reg_repo.count_by_user(user_id),
        "schedules": schedule_repo.count_by_user(user_id),
    }
