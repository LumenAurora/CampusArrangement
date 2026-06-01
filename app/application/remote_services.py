from __future__ import annotations

from datetime import datetime

from app.domain.models import (
    Activity,
    ActivityStatus,
    AllocationMode,
    Registration,
    RegistrationStatus,
    Role,
    SignupMode,
    TimeSlot,
    User,
)
from app.infrastructure.api_client import ApiClient


class RemoteUserService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def register(self, username: str, password: str, role: Role) -> User:
        payload = self._api.post("/users", json={"username": username, "password": password, "role": role.value})
        return User(id=payload["id"], username=payload["username"], role=Role(payload["role"]))

    def authenticate(self, username: str, password: str) -> User:
        return self._api.login(username, password)

    def delete_user(self, current_user: User, user_id: str) -> bool:
        self._api._request("DELETE", f"/users/{user_id}")
        return True


class RemoteActivityService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def create_activity(
        self,
        user: User,
        name: str,
        signup_start: datetime,
        signup_end: datetime,
        details: str,
        signup_mode: SignupMode = SignupMode.REALTIME,
        allocation_mode: AllocationMode = AllocationMode.GREEDY,
    ) -> Activity:
        payload = self._api.post(
            "/activities",
            json={
                "name": name,
                "signup_start": signup_start.isoformat(),
                "signup_end": signup_end.isoformat(),
                "details": details,
                "signup_mode": signup_mode.value,
                "allocation_mode": allocation_mode.value,
            },
        )
        return Activity(
            id=payload["id"],
            name=payload["name"],
            status=ActivityStatus(payload["status"]),
            owner_id=payload["owner_id"],
            signup_start=datetime.fromisoformat(payload["signup_start"]),
            signup_end=datetime.fromisoformat(payload["signup_end"]),
            details=payload["details"],
            signup_mode=SignupMode(payload["signup_mode"]),
            allocation_mode=AllocationMode(payload["allocation_mode"]),
        )

    def add_slot(
        self,
        user: User,
        activity_id: str,
        start_time: datetime,
        end_time: datetime,
        capacity: int,
    ) -> TimeSlot:
        payload = self._api.post(
            f"/activities/{activity_id}/slots",
            json={
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "capacity": capacity,
            },
        )
        return TimeSlot(
            id=payload["id"],
            activity_id=payload["activity_id"],
            start_time=datetime.fromisoformat(payload["start_time"]),
            end_time=datetime.fromisoformat(payload["end_time"]),
            capacity=payload["capacity"],
            used_count=payload["used_count"],
        )

    def list_activities(self) -> list[dict]:
        return self._api.get("/activities")

    def list_slots(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/activities/{activity_id}/slots")

    def get_activity(self, activity_id: str) -> dict | None:
        return self._api.get(f"/activities/{activity_id}")

    def delete_activity(self, user: User, activity_id: str) -> bool:
        self._api._request("DELETE", f"/activities/{activity_id}")
        return True

    def publish_activity(self, user: User, activity_id: str) -> None:
        self._api._request("PATCH", f"/activities/{activity_id}/status", json={"action": "publish"})

    def close_activity(self, user: User, activity_id: str) -> None:
        self._api._request("PATCH", f"/activities/{activity_id}/status", json={"action": "close"})

    def archive_activity(self, user: User, activity_id: str) -> None:
        self._api._request("PATCH", f"/activities/{activity_id}/status", json={"action": "archive"})


class RemoteRegistrationService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def register(self, user_id: str, activity_id: str, slot_id: str, priority: int) -> Registration:
        payload = self._api.post(
            "/registrations",
            json={"activity_id": activity_id, "slot_id": slot_id, "priority": priority},
        )
        return Registration(
            id=payload["id"],
            user_id=payload["user_id"],
            activity_id=payload["activity_id"],
            slot_id=payload["slot_id"],
            priority=payload["priority"],
            status=RegistrationStatus(payload["status"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
        )


class RemoteSchedulingService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def run(self, activity_id: str) -> int:
        payload = self._api.post("/scheduling/run", json={"activity_id": activity_id})
        return int(payload.get("count", 0))
