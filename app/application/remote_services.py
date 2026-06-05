from __future__ import annotations

from datetime import datetime

from app.domain.models import (
    Activity,
    ActivityStatus,
    AllocationMode,
    CheckIn,
    CheckInMode,
    CheckInStatus,
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
        self._api.post(f"/users/{user_id}/delete", json={})
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
        location: str = "",
        checkin_mode: str = "manual",
        checkin_start: datetime | None = None,
        checkin_end: datetime | None = None,
    ) -> Activity:
        json_data = {
            "name": name,
            "signup_start": signup_start.isoformat(),
            "signup_end": signup_end.isoformat(),
            "details": details,
            "signup_mode": signup_mode.value,
            "allocation_mode": allocation_mode.value,
            "location": location,
            "checkin_mode": checkin_mode,
        }
        if checkin_start:
            json_data["checkin_start"] = checkin_start.isoformat()
        if checkin_end:
            json_data["checkin_end"] = checkin_end.isoformat()
        payload = self._api.post("/activities", json=json_data)
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
            location=payload.get("location", ""),
            checkin_code=payload.get("checkin_code", ""),
            checkin_mode=CheckInMode(payload.get("checkin_mode", "manual")),
            checkin_start=datetime.fromisoformat(payload["checkin_start"]) if payload.get("checkin_start") else None,
            checkin_end=datetime.fromisoformat(payload["checkin_end"]) if payload.get("checkin_end") else None,
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

    def list_open_activities(self) -> list[dict]:
        return self._api.get("/activities", params={"status": "open"})

    def list_slots(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/activities/{activity_id}/slots")

    def get_activity(self, activity_id: str) -> dict | None:
        return self._api.get(f"/activities/{activity_id}")

    def delete_activity(self, user: User, activity_id: str) -> bool:
        self._api.post(f"/activities/{activity_id}/delete", json={})
        return True

    def publish_activity(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "publish"})

    def close_activity(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "close"})

    def reopen_activity(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "reopen"})

    def archive_activity(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "archive"})

    def submit_for_review(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "submit_review"})

    def reject_activity(self, user: User, activity_id: str) -> None:
        self._api.post(f"/activities/{activity_id}/status", json={"action": "reject"})


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

    def cancel(self, user_id: str, registration_id: str) -> None:
        self._api.post(f"/registrations/{registration_id}/cancel", json={})

    def list_user_registrations(self, user_id: str) -> list[dict]:
        return self._api.get("/registrations", params={"user_id": user_id})


class RemoteSchedulingService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def run(self, activity_id: str) -> int:
        payload = self._api.post("/scheduling/run", json={"activity_id": activity_id})
        return int(payload.get("count", 0))


class RemoteCheckInService:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def check_in(self, user: User, activity_id: str, user_id: str, slot_id: str) -> CheckIn:
        payload = self._api.post(
            "/checkins",
            json={"activity_id": activity_id, "user_id": user_id, "slot_id": slot_id},
        )
        return CheckIn(
            id=payload["id"],
            activity_id=payload["activity_id"],
            user_id=payload["user_id"],
            slot_id=payload["slot_id"],
            status=CheckInStatus(payload["status"]),
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            photo_path=payload.get("photo_path", ""),
        )

    def mark_absent(self, user: User, activity_id: str, user_id: str, slot_id: str) -> None:
        self._api.post("/checkins/absent", json={"activity_id": activity_id, "user_id": user_id, "slot_id": slot_id})

    def unmark_absent(self, user: User, activity_id: str, user_id: str, slot_id: str) -> None:
        self._api.post("/checkins/unmark_absent", json={"activity_id": activity_id, "user_id": user_id, "slot_id": slot_id})

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get("/checkins", params={"activity_id": activity_id})

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._api.get("/checkins", params={"user_id": user_id})

    def self_check_in(self, user_id: str, activity_id: str, slot_id: str, checkin_code: str) -> CheckIn:
        payload = self._api.post(
            "/checkins/self",
            json={"activity_id": activity_id, "slot_id": slot_id, "checkin_code": checkin_code},
        )
        return CheckIn(
            id=payload["id"],
            activity_id=payload["activity_id"],
            user_id=payload["user_id"],
            slot_id=payload["slot_id"],
            status=CheckInStatus(payload["status"]),
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            photo_path=payload.get("photo_path", ""),
        )

    def location_check_in(
        self,
        user_id: str,
        activity_id: str,
        slot_id: str,
        latitude: float,
        longitude: float,
    ) -> CheckIn:
        payload = self._api.post(
            "/checkins/location",
            json={"activity_id": activity_id, "slot_id": slot_id, "latitude": latitude, "longitude": longitude},
        )
        return CheckIn(
            id=payload["id"],
            activity_id=payload["activity_id"],
            user_id=payload["user_id"],
            slot_id=payload["slot_id"],
            status=CheckInStatus(payload["status"]),
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            photo_path=payload.get("photo_path", ""),
        )

    def photo_check_in(
        self,
        user_id: str,
        activity_id: str,
        slot_id: str,
        photo_path: str,
    ) -> CheckIn:
        payload = self._api.post(
            "/checkins/photo",
            json={"activity_id": activity_id, "slot_id": slot_id, "photo_path": photo_path},
        )
        return CheckIn(
            id=payload["id"],
            activity_id=payload["activity_id"],
            user_id=payload["user_id"],
            slot_id=payload["slot_id"],
            status=CheckInStatus(payload["status"]),
            checked_at=datetime.fromisoformat(payload["checked_at"]),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            photo_path=payload.get("photo_path", ""),
        )

    def get_checkin_stats(self, activity_id: str) -> dict:
        return self._api.get(f"/activities/{activity_id}/checkin_stats")

    def generate_checkin_code(self, user: User, activity_id: str) -> str:
        payload = self._api.post(f"/activities/{activity_id}/generate_checkin_code", json={})
        return payload.get("checkin_code", "")
