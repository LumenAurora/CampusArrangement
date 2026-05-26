from __future__ import annotations

import time

from app.infrastructure.api_client import ApiClient


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

    def get(self, activity_id: str) -> dict | None:
        return self._api.get(f"/activities/{activity_id}")

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("activities", 0))


class RemoteTimeSlotRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/activities/{activity_id}/slots")

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("slots", 0))


class RemoteRegistrationRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("registrations", 0))

    def count_by_user(self, user_id: str) -> int:
        return int(self._metrics.get_user_metrics(user_id).get("registrations", 0))


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


class RemoteUserRepository:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def list_all(self) -> list[dict]:
        return self._api.get("/users")
