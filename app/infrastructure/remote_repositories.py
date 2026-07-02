from __future__ import annotations

from pathlib import Path
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
        action_map = {
            "open": "publish",
            "closed": "close",
            "archived": "archive",
            "pending_review": "submit_review",
            "draft": "reject",
        }
        status_val = status.value if hasattr(status, 'value') else status
        # 特殊处理：从closed回滚到open使用reopen动作
        if status_val == "open":
            # 检查当前活动状态来决定是publish还是reopen
            activity = self.get(activity_id)
            if activity and activity.get("status") == "closed":
                action = "reopen"
            else:
                action = "publish"
        else:
            action = action_map.get(status_val)
        if not action:
            from app.domain.exceptions import ValidationError
            raise ValidationError(f"不支持的活动状态变更: {status_val}")
        self._api.post(f"/activities/{activity_id}/status", json={"action": action})

    def delete(self, activity_id: str) -> bool:
        self._api.post(f"/activities/{activity_id}/delete", json={})
        return True

    def update_checkin_code(self, activity_id: str, checkin_code: str) -> None:
        # Server generates its own code via the API endpoint.
        # We store the server-returned code so callers can retrieve it.
        self._api.post(f"/activities/{activity_id}/generate_checkin_code", json={})

    def update_checkin_closed(self, activity_id: str, closed: bool) -> None:
        # 远程模式：通过 close/reopen 端点切换签到关闭状态
        action = "close" if closed else "reopen"
        self._api.post(f"/checkin/{activity_id}/{action}", json={})


class RemoteTimeSlotRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def get(self, slot_id: str) -> dict | None:
        try:
            return self._api.get(f"/slots/{slot_id}")
        except Exception:
            return None

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._api.get(f"/activities/{activity_id}/slots")

    def list_positions(self, parent_slot_id: str) -> list[dict]:
        """获取某时段下的所有子岗位（远程模式）"""
        return self._api.get(f"/slots/{parent_slot_id}/positions")

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("slots", 0))

    def count_by_activity_status(self, status_value: str) -> int:
        result = self._api.get("/metrics/slots-count", params={"status": status_value})
        return int(result.get("count", 0))

    def lock_slot(self, slot_id: str) -> bool:
        # Slot locking is handled server-side during registration
        # Return True to allow the registration flow to proceed
        return True

    def release_slot(self, slot_id: str) -> None:
        # Slot release is handled server-side during cancellation
        pass

    def reset_used_counts_for_activity(self, activity_id: str) -> None:
        # Handled server-side during scheduling
        pass

    def increment_used_count(self, slot_id: str, count: int = 1) -> None:
        # Handled server-side during scheduling
        pass

    to_models = TimeSlotRepository.to_models


class RemoteRegistrationRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def create(self, registration) -> None:
        # Remote registration is handled server-side via /registrations
        pass

    def get(self, registration_id: str) -> dict | None:
        try:
            return self._api.get(f"/registrations/{registration_id}")
        except Exception:
            return None

    def list_by_user_activity(self, user_id: str, activity_id: str) -> list[dict]:
        user_regs = self._api.get("/registrations", params={"user_id": user_id})
        return [r for r in user_regs if r.get("activity_id") == activity_id and r.get("status") not in ("cancelled",)]

    def list_pending(self, activity_id: str) -> list[dict]:
        regs = self._api.get("/registrations", params={"activity_id": activity_id, "status": "pending"})
        return regs

    def reset_for_rescheduling(self, activity_id: str) -> None:
        # Handled server-side during scheduling
        pass

    def list_by_user(self, user_id: str) -> list[dict]:
        regs = self._api.get("/registrations", params={"user_id": user_id})
        return [r for r in regs if r.get("status") not in ("cancelled",)]

    def update_status(self, registration_id: str, status) -> None:
        status_val = status.value if hasattr(status, 'value') else status
        if status_val == "cancelled":
            self._api.post(f"/registrations/{registration_id}/cancel", json={})
        # assigned/confirmed status changes are handled server-side during scheduling

    def count_all(self) -> int:
        return int(self._metrics.get_overview().get("registrations", 0))

    def count_by_user(self, user_id: str) -> int:
        return int(self._metrics.get_user_metrics(user_id).get("registrations", 0))

    to_models = RegistrationRepository.to_models


class RemoteScheduleRepository:
    def __init__(self, api_client: ApiClient, metrics_cache: MetricsCache) -> None:
        self._api = api_client
        self._metrics = metrics_cache

    def create(self, result) -> None:
        # Remote scheduling is handled server-side via /scheduling/run
        pass

    def clear_for_activity(self, activity_id: str) -> None:
        # Remote scheduling is handled server-side via /scheduling/run
        pass

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
        try:
            return self._api.get(f"/checkins/{checkin_id}")
        except Exception:
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
        # Status updates are handled server-side via checkin_service methods
        pass


class RemoteUserRepository:
    def __init__(self, api_client: ApiClient) -> None:
        self._api = api_client

    def list_all(self) -> list[dict]:
        return self._api.get("/users")

    def get_by_username(self, username: str) -> dict | None:
        users = self._api.get("/users", params={"username": username})
        if isinstance(users, list):
            for user in users:
                if user.get("username") == username:
                    return user
        elif isinstance(users, dict) and users.get("username") == username:
            return users
        return None

    def get_by_id(self, user_id: str) -> dict | None:
        try:
            return self._api.get(f"/users/{user_id}")
        except Exception:
            try:
                current_user = self._api.get("/users/me")
            except Exception:
                return None
            return current_user if current_user.get("id") == user_id else None

    def update_avatar(self, user_id: str, avatar_path: str) -> None:
        upload_root = Path(__file__).resolve().parent.parent / "resources" / "uploads"
        full_path = upload_root / avatar_path
        self._api.post_file("/users/me/avatar", "file", str(full_path))

    def update_notification_mode(self, user_id: str, mode) -> None:
        # 远程模式：调用 PUT /users/me/settings 更新通知偏好
        mode_val = mode.value if hasattr(mode, "value") else str(mode)
        self._api.put("/users/me/settings", json={"notification_mode": mode_val})
