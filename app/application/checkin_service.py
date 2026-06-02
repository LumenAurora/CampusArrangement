from __future__ import annotations

from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import CheckIn, CheckInStatus, Role, User
from app.infrastructure.repositories import CheckInRepository, ScheduleRepository


class CheckInService:
    def __init__(self, checkin_repo: CheckInRepository, schedule_repo: ScheduleRepository | None = None) -> None:
        self._checkin_repo = checkin_repo
        self._schedule_repo = schedule_repo

    def check_in(self, user: User, activity_id: str, user_id: str, slot_id: str) -> CheckIn:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可执行签到")
        existing = self._checkin_repo.get_by_user_slot(user_id, slot_id)
        if existing:
            raise ConflictError("该用户已签到此时段")
        if self._schedule_repo:
            results = self._schedule_repo.list_by_activity(activity_id)
            if not any(r["user_id"] == user_id and r["slot_id"] == slot_id for r in results):
                raise ValidationError("该用户未被分配到此时段，无法签到")
        checkin = CheckIn.create(
            activity_id=activity_id,
            user_id=user_id,
            slot_id=slot_id,
            status=CheckInStatus.CHECKED_IN,
        )
        self._checkin_repo.create(checkin)
        return checkin

    def mark_absent(self, user: User, checkin_id: str) -> None:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可标记缺勤")
        checkin = self._checkin_repo.get(checkin_id)
        if not checkin:
            raise ValidationError("签到记录不存在")
        if checkin["status"] == CheckInStatus.ABSENT.value:
            raise ValidationError("该用户已被标记为缺勤")
        self._checkin_repo.update_status(checkin_id, CheckInStatus.ABSENT)

    def list_by_activity(self, activity_id: str) -> list[dict]:
        return self._checkin_repo.list_by_activity(activity_id)

    def list_by_user(self, user_id: str) -> list[dict]:
        return self._checkin_repo.list_by_user(user_id)
