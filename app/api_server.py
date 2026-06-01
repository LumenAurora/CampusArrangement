from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.application.activity_service import ActivityService
from app.application.registration_service import RegistrationService
from app.application.scheduling_service import SchedulingService
from app.application.user_service import UserService
from app.domain.exceptions import CapacityExceeded, PermissionDenied, ValidationError
from app.domain.models import AllocationMode, Role, SignupMode, User
from app.infrastructure.db import init_db
from app.infrastructure.repositories import (
    ActivityRepository,
    RegistrationRepository,
    ScheduleRepository,
    TimeSlotRepository,
    UserRepository,
)

app = FastAPI(title="Campus Scheduler API", version="1.0")

init_db()
user_repo = UserRepository()
activity_repo = ActivityRepository()
slot_repo = TimeSlotRepository()
reg_repo = RegistrationRepository()
schedule_repo = ScheduleRepository()

user_service = UserService(user_repo)
activity_service = ActivityService(activity_repo, slot_repo)
registration_service = RegistrationService(slot_repo, reg_repo, activity_repo)
scheduling_service = SchedulingService(reg_repo, slot_repo, schedule_repo, activity_repo)

_tokens: dict[str, str] = {}


def _ensure_admin() -> None:
    if user_repo.get_by_username("admin"):
        return
    user_service.register(username="admin", password="admin", role=Role.SUPER_ADMIN)


_ensure_admin()


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


def _to_user(record: dict) -> User:
    return User(id=record["id"], username=record["username"], role=Role(record["role"]))


def _get_current_user(authorization: Optional[str] = Header(None)) -> User:
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少认证信息")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="认证信息无效")
    token = parts[1].strip()
    user_id = _tokens.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="登录已失效")
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
    _tokens[token] = user.id
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


@app.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN})
    try:
        user_service.delete_user(current_user, user_id)
    except Exception as exc:
        _handle_domain_error(exc)
        raise
    return {"ok": True}


@app.get("/activities")
def list_activities(_: User = Depends(_get_current_user)) -> list[dict]:
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
    }


@app.delete("/activities/{activity_id}")
def delete_activity(activity_id: str, current_user: User = Depends(_get_current_user)) -> dict:
    try:
        activity_service.delete_activity(user=current_user, activity_id=activity_id)
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


@app.post("/scheduling/run")
def run_scheduling(payload: ScheduleRunRequest, current_user: User = Depends(_get_current_user)) -> dict:
    _require_roles(current_user, {Role.SUPER_ADMIN, Role.ORGANIZER})
    count = scheduling_service.run(payload.activity_id)
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
