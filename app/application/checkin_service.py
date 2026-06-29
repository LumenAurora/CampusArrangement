from __future__ import annotations

import math
import secrets
from datetime import datetime, timezone

from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import ActivityStatus, CheckIn, CheckInMode, CheckInStatus, Role, User
from app.infrastructure.repositories import ActivityRepository, CheckInRepository, ScheduleRepository


# 地球半径（公里），用于Haversine公式
_EARTH_RADIUS_KM = 6371.0
# 默认签到距离阈值（米）
_DEFAULT_MAX_DISTANCE_M = 500


class CheckInService:
    def __init__(
        self,
        checkin_repo: CheckInRepository,
        schedule_repo: ScheduleRepository,
        activity_repo: ActivityRepository,
    ) -> None:
        self._checkin_repo = checkin_repo
        self._schedule_repo = schedule_repo
        self._activity_repo = activity_repo

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        """将任意 datetime 统一转为 UTC-aware，用于与 now(UTC) 比较。

        naive datetime 会被视为本地时间正确转换；
        aware datetime 也会统一转换到 UTC 时区。
        """
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _check_owner_or_admin(user: User, activity: dict) -> None:
        """校验调用者是超级管理员或活动拥有者，防止 ORGANIZER 越权操作他人活动。"""
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅管理员或组织者可执行此操作")
        if user.role != Role.SUPER_ADMIN and activity.get("owner_id") != user.id:
            raise PermissionDenied("无权操作该活动")

    def _validate_checkin_allowed(self, activity: dict) -> None:
        """校验活动状态和签到时间窗口。

        允许签到的状态：
        - CLOSED / ARCHIVED：报名已结束，始终允许签到（受签到窗口约束）。
        - OPEN：仅当活动配置了签到时间窗口时允许签到（支持"边报名边签到"场景）。

        人工提前结束签到（checkin_closed=True）优先于时间窗口判定。
        """
        status = activity["status"]
        allowed_statuses = {ActivityStatus.CLOSED.value, ActivityStatus.ARCHIVED.value}
        if status == ActivityStatus.OPEN.value:
            # OPEN 状态需要配置了签到窗口才允许签到
            if not activity.get("checkin_start") and not activity.get("checkin_end"):
                raise ValidationError("活动报名中且未设置签到时间窗口，请先关闭报名或设置签到窗口")
        elif status not in allowed_statuses:
            raise ValidationError("该活动当前不在可签到状态")
        # 人工提前结束签到：最高优先级，直接拒绝
        if activity.get("checkin_closed"):
            raise ValidationError("签到已结束")
        now = datetime.now(timezone.utc)
        checkin_start = activity.get("checkin_start")
        checkin_end = activity.get("checkin_end")
        if checkin_start:
            start = datetime.fromisoformat(checkin_start) if isinstance(checkin_start, str) else checkin_start
            start = self._to_utc(start)
            if now < start:
                raise ValidationError("签到尚未开始")
        if checkin_end:
            end = datetime.fromisoformat(checkin_end) if isinstance(checkin_end, str) else checkin_end
            end = self._to_utc(end)
            if now > end:
                raise ValidationError("签到已结束")

    def close_checkin(self, user: User, activity_id: str) -> None:
        """人工提前结束签到。与 checkin_end 时间独立，可逆（reopen_checkin 恢复）。"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅管理员或组织者可结束签到")
        if user.role != Role.SUPER_ADMIN and activity.get("owner_id") != user.id:
            raise PermissionDenied("无权操作该活动")
        if activity.get("checkin_closed"):
            raise ValidationError("签到已结束，无需重复操作")
        self._activity_repo.update_checkin_closed(activity_id, True)

    def reopen_checkin(self, user: User, activity_id: str) -> None:
        """恢复签到（撤销人工提前结束）。仅在 checkin_end 时间未过期时生效。"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅管理员或组织者可恢复签到")
        if user.role != Role.SUPER_ADMIN and activity.get("owner_id") != user.id:
            raise PermissionDenied("无权操作该活动")
        if not activity.get("checkin_closed"):
            raise ValidationError("签到未被人工结束，无需恢复")
        self._activity_repo.update_checkin_closed(activity_id, False)

    def check_in(self, user: User, activity_id: str, user_id: str, slot_id: str) -> CheckIn:
        """管理员手动签到"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        self._validate_checkin_allowed(activity)
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            raise ConflictError("该用户已签到此时段")
        results = self._schedule_repo.list_by_activity(activity_id)
        if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
            raise ValidationError("该用户未被分配到此时段，无法签到")
        checkin = CheckIn.create(activity_id=activity_id, user_id=user_id, slot_id=slot_id)
        self._checkin_repo.create(checkin)
        return checkin

    def mark_absent(self, user: User, activity_id: str, user_id: str, slot_id: str) -> CheckIn:
        """标记缺勤"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            if existing["status"] == CheckInStatus.ABSENT.value:
                raise ValidationError("该用户已被标记缺勤")
            # 保留原始 checked_at，避免覆盖用户实际签到时间
            self._checkin_repo.update_status(existing["id"], CheckInStatus.ABSENT, keep_checked_at=True)
            return CheckIn(
                id=existing["id"], activity_id=activity_id, user_id=user_id,
                slot_id=slot_id, status=CheckInStatus.ABSENT,
                checked_at=existing["checked_at"],
                latitude=existing.get("latitude"), longitude=existing.get("longitude"),
                photo_path=existing.get("photo_path", ""),
            )
        results = self._schedule_repo.list_by_activity(activity_id)
        if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
            raise ValidationError("该用户未被分配到此时段")
        checkin = CheckIn.create(activity_id=activity_id, user_id=user_id, slot_id=slot_id, status=CheckInStatus.ABSENT)
        self._checkin_repo.create(checkin)
        return checkin

    def unmark_absent(self, user: User, activity_id: str, user_id: str, slot_id: str) -> None:
        """取消缺勤标记，恢复为已签到"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if not existing:
            raise ValidationError("该用户无签到记录")
        if existing["status"] != CheckInStatus.ABSENT.value:
            raise ValidationError("该用户未被标记缺勤")
        self._checkin_repo.update_status(existing["id"], CheckInStatus.CHECKED_IN, keep_checked_at=True)

    def self_check_in(self, user_id: str, activity_id: str, slot_id: str, checkin_code: str) -> CheckIn:
        """用户自助签到码签到"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity.get("checkin_mode") not in (CheckInMode.SELF_CODE.value, CheckInMode.QRCODE.value):
            raise ValidationError("该活动不支持自助签到码签到")
        self._validate_checkin_allowed(activity)
        # 拦截空签到码：避免活动未生成签到码或用户传入空值时被 "" != "" 误判绕过
        if not activity.get("checkin_code") or not checkin_code:
            raise ValidationError("签到码未生成或无效，请联系管理员生成签到码")
        if activity.get("checkin_code") != checkin_code:
            raise ValidationError("签到码无效")
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            raise ConflictError("您已签到此时段")
        results = self._schedule_repo.list_by_activity(activity_id)
        if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
            raise ValidationError("您未被分配到此时段，无法签到")
        checkin = CheckIn.create(activity_id=activity_id, user_id=user_id, slot_id=slot_id)
        self._checkin_repo.create(checkin)
        return checkin

    def location_check_in(
        self,
        user_id: str,
        activity_id: str,
        slot_id: str,
        latitude: float,
        longitude: float,
    ) -> CheckIn:
        """位置签到"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity.get("checkin_mode") != CheckInMode.LOCATION.value:
            raise ValidationError("该活动不支持位置签到")
        self._validate_checkin_allowed(activity)
        # 验证位置距离：LOCATION 模式下 location 必须是有效的"纬度,经度"坐标，
        # 缺失或格式异常时必须拒绝签到，避免无校验直接放行。
        location_str = activity.get("location", "")
        if not location_str or "," not in location_str:
            raise ValidationError("活动地点坐标未配置或格式异常，无法进行位置签到")
        try:
            parts = location_str.split(",")
            act_lat = float(parts[0].strip())
            act_lon = float(parts[1].strip())
            distance = _haversine_km(act_lat, act_lon, latitude, longitude)
            if distance * 1000 > _DEFAULT_MAX_DISTANCE_M:
                raise ValidationError(f"您距离活动地点过远（{distance * 1000:.0f}米），无法签到")
        except (ValueError, IndexError):
            raise ValidationError("活动地点坐标格式异常，无法进行位置签到")
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            raise ConflictError("您已签到此时段")
        results = self._schedule_repo.list_by_activity(activity_id)
        if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
            raise ValidationError("您未被分配到此时段，无法签到")
        checkin = CheckIn.create(
            activity_id=activity_id, user_id=user_id, slot_id=slot_id,
            latitude=latitude, longitude=longitude,
        )
        self._checkin_repo.create(checkin)
        return checkin

    def photo_check_in(
        self,
        user_id: str,
        activity_id: str,
        slot_id: str,
        photo_path: str,
    ) -> CheckIn:
        """拍照签到"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        if activity.get("checkin_mode") != CheckInMode.PHOTO.value:
            raise ValidationError("该活动不支持拍照签到")
        self._validate_checkin_allowed(activity)
        if not photo_path:
            raise ValidationError("请上传照片")
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            raise ConflictError("您已签到此时段")
        results = self._schedule_repo.list_by_activity(activity_id)
        if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
            raise ValidationError("您未被分配到此时段，无法签到")
        checkin = CheckIn.create(
            activity_id=activity_id, user_id=user_id, slot_id=slot_id,
            photo_path=photo_path,
        )
        self._checkin_repo.create(checkin)
        return checkin

    def generate_checkin_code(self, user: User, activity_id: str) -> str:
        """生成签到码（支持SELF_CODE和QRCODE模式）"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        self._check_owner_or_admin(user, activity)
        if activity.get("checkin_mode") not in (CheckInMode.SELF_CODE.value, CheckInMode.QRCODE.value):
            raise ValidationError("该活动签到模式不支持生成签到码")
        code = secrets.token_hex(4).upper()
        self._activity_repo.update_checkin_code(activity_id, code)
        return code

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._checkin_repo.list_by_activity(activity_id)

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._checkin_repo.list_by_user(user_id)

    def get_checkin_stats(self, activity_id: str) -> dict:
        """获取签到统计"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            raise ValidationError("活动不存在")
        results = self._schedule_repo.list_by_activity(activity_id)
        checkins = self._checkin_repo.list_by_activity(activity_id)
        total_assigned = len(results)
        checked_in = sum(1 for c in checkins if c["status"] == CheckInStatus.CHECKED_IN.value)
        absent = sum(1 for c in checkins if c["status"] == CheckInStatus.ABSENT.value)
        not_checked_in = max(0, total_assigned - checked_in - absent)
        # 按时段统计
        slot_stats: dict[str, dict] = {}
        for r in results:
            sid = r["slot_id"]
            if sid not in slot_stats:
                slot_stats[sid] = {"slot_id": sid, "assigned": 0, "checked_in": 0, "absent": 0}
            slot_stats[sid]["assigned"] += 1
        for c in checkins:
            sid = c["slot_id"]
            if sid in slot_stats:
                if c["status"] == CheckInStatus.CHECKED_IN.value:
                    slot_stats[sid]["checked_in"] += 1
                elif c["status"] == CheckInStatus.ABSENT.value:
                    slot_stats[sid]["absent"] += 1
        return {
            "total_assigned": total_assigned,
            "checked_in": checked_in,
            "absent": absent,
            "not_checked_in": not_checked_in,
            "slots": list(slot_stats.values()),
        }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点之间的Haversine距离（公里）"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return _EARTH_RADIUS_KM * c
