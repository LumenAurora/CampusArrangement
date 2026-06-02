from __future__ import annotations

import time

from app.infrastructure.api_client import ApiClient
from app.infrastructure.repositories import RegistrationRepository, TimeSlotRepository


class MetricsCache:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client
        self._overview: dict | None = None
        self._overview_at = 0.0
        self._user_cache: dict[str, tuple[float, dict]] = {}

    def get_overview(self) -> dict:
        now = time.monotonic()
        if not self._overview or now - self._overview_at > 1:
            self._overview = self._api.get("/metrics/overview")
            self._overview_at = now
        return self._overview

    def get_user_metrics(self, user_id: str) -> dict:
        now = time.monotonic()
        cached = self._user_cache.get(user_id)
        if not cached or now - cached[0] > 1:
            payload = self._api.get(f"/metrics/users/{user_id}")
            self._user_cache[user_id] = (now, payload)
            return payload
        return cached[1]


class RemoteActivityRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def list_all(self) -> list[dict]:
        return self._api.get("/activities")

    def list_by_status(self, status) -> list[dict]:
        status_val = status.value if hasattr(status, 'value') else status
        return self._api.get("/activities", params={"status": status_val})

    def get(self, activity_id: str) -> dict | None:
        return self._api.get(f"/activities/{activity_id}")

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("activities", 0))

    def count_by_status(self, status) -> int:
        status_val = status.value if hasattr(status, 'value') else status
        return len(self._api.get("/activities", params={"status": status_val}))

    def update_status(self, activity_id: str, status) -> None:
        action_map = {"open": "publish", "closed": "close", "archived": "archive"}
        status_val = status.value if hasattr(status, 'value') else status
        action = action_map.get(status_val)
        if not action:
            raise ValueError(f"不支持的活动状态变更: {status_val}")
        self._api.post(f"/activities/{activity_id}/status", json={"action": action})

    def delete(self, activity_id: str) -> bool:
        self._api.post(f"/activities/{activity_id}/delete", json={})
        return True


class RemoteTimeSlotRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def get(self, slot_id: str) -> dict | None:
        all_activities = self._api.get("/activities")
        for activity in all_activities:
            for slot in self._api.get(f"/activities/{activity['id']}/slots"):
                if slot["id"] == slot_id:
                    return slot
        return None

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/activities/{activity_id}/slots")

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("slots", 0))

    def count_by_activity_status(self, status_value: str) -> int:
        activities = self._api.get("/activities", params={"status": status_value})
        total = 0
        for activity in activities:
            slots = self._api.get(f"/activities/{activity['id']}/slots")
            total += len(slots)
        return total

    to_models = TimeSlotRepository.to_models


class RemoteRegistrationRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def get(self, registration_id: str) -> dict | None:
        all_activities = self._api.get("/activities")
        for activity in all_activities:
            regs = self._api.get("/registrations", params={"activity_id": activity["id"]})
            for reg in regs:
                if reg["id"] == registration_id:
                    return reg
        return None

    def list_by_user_activity(self, user_id: str, activity_id: str) -> list[dict]:
        user_regs = self._api.get("/registrations", params={"user_id": user_id})
        return [r for r in user_regs if r.get("activity_id") == activity_id and r.get("status") != "cancelled"]

    def list_pending(self, activity_id: str) -> list[dict]:
        return self._api.get("/registrations", params={"activity_id": activity_id})

    def update_status(self, registration_id: str, status) -> None:
        status_val = status.value if hasattr(status, 'value') else status
        if status_val == "cancelled":
            self._api.post(f"/registrations/{registration_id}/cancel", json={})
        elif status_val == "assigned":
            self._api.post(f"/registrations/{registration_id}/assign", json={})

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("registrations", 0))

    def count_by_user(self, user_id: str) -> int:
        return int(self._metrics.get_user_metrics(user_id).get("registrations", 0))

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._api.get("/registrations", params={"user_id": user_id})

    to_models = RegistrationRepository.to_models


class RemoteScheduleRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get("/schedules", params={"activity_id": activity_id})

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._api.get("/schedules", params={"user_id": user_id})

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("schedules", 0))

    def count_by_user(self, user_id: str) -> int:
        return int(self._metrics.get_user_metrics(user_id).get("schedules", 0))


class RemoteCheckInRepository:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def get(self, checkin_id: str) -> dict | None:
        all_activities = self._api.get("/activities")
        for activity in all_activities:
            checkins = self._api.get("/checkins", params={"activity_id": activity["id"]})
            for ci in checkins:
                if ci.get("id") == checkin_id:
                    return ci
        return None

    def get_by_user_slot(self, user_id: str, slot_id: str) -> dict | None:
        checkins = self._api.get("/checkins", params={"user_id": user_id})
        for ci in checkins:
            if ci.get("slot_id") == slot_id:
                return ci
        return None

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/checkins", params={"activity_id": activity_id})

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._api.get(f"/checkins", params={"user_id": user_id})

    def count_by_activity(self, activity_id: str) -> int:
        return len([ci for ci in self.list_by_activity(activity_id) if ci.get("status") == "checked_in"])

    def update_status(self, checkin_id: str, status) -> None:
        status_val = status.value if hasattr(status, 'value') else status
        if status_val == "absent":
            self._api.post(f"/checkins/{checkin_id}/absent", json={})
        elif status_val == "checked_in":
            self._api.post(f"/checkins/{checkin_id}/revert", json={})


class RemoteUserRepository:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def list_all(self) -> list[dict]:
        return self._api.get("/users")

    def get_by_username(self, username: str) -> dict | None:
        for user in self.list_all():
            if user["username"] == username:
                return user
        return None

    def get_by_id(self, user_id: str) -> dict | None:
        for user in self.list_all():
            if user["id"] == user_id:
                return user
        return None
