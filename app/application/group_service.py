from __future__ import annotations

from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import Group, GroupMember, GroupRole, MemberStatus, Role, User
from app.infrastructure.repositories import ActivityRepository, GroupRepository


class GroupService:
    def __init__(self, group_repo: GroupRepository, activity_repo: ActivityRepository) -> None:
        self._repo = group_repo
        self._activity_repo = activity_repo

    # ── 小组 CRUD ──────────────────────────────────────────

    def create_group(self, user: User, name: str, description: str = "") -> Group:
        if user.role not in {Role.SUPER_ADMIN, Role.ORGANIZER}:
            raise PermissionDenied("仅组织者或管理员可创建小组")
        if not name or not name.strip():
            raise ValidationError("小组名称不能为空")
        group = Group.create(name=name.strip(), owner_id=user.id, description=description.strip())
        self._repo.create(group)
        # 创建者自动成为小组管理员（已审批）
        self._repo.add_member(group.id, user.id, role=GroupRole.ADMIN.value, status=MemberStatus.APPROVED.value)
        return group

    def get_group(self, group_id: str) -> dict | None:
        return self._repo.get(group_id)

    def list_all_groups(self) -> list[dict]:
        return self._repo.list_all()

    def list_my_groups(self, user: User) -> list[dict]:
        """获取用户管理的和所属的小组"""
        owned = self._repo.list_by_owner(user.id)
        member_of = self._repo.list_by_user(user.id)
        # 合并去重
        seen = set()
        result = []
        for g in owned + member_of:
            if g["id"] not in seen:
                seen.add(g["id"])
                result.append(g)
        return sorted(result, key=lambda g: g.get("created_at", ""), reverse=True)

    def delete_group(self, user: User, group_id: str) -> None:
        group = self._repo.get(group_id)
        if not group:
            raise ValidationError("小组不存在")
        if user.role != Role.SUPER_ADMIN and group["owner_id"] != user.id:
            raise PermissionDenied("只能删除自己创建的小组")
        self._repo.delete(group_id)

    # ── 成员管理 ──────────────────────────────────────────

    def join_group(self, user_id: str, group_id: str) -> None:
        """用户申请加入小组"""
        group = self._repo.get(group_id)
        if not group:
            raise ValidationError("小组不存在")
        existing = self._repo.get_member(group_id, user_id)
        if existing:
            if existing["status"] == MemberStatus.APPROVED.value:
                raise ValidationError("您已是该小组成员")
            if existing["status"] == MemberStatus.PENDING.value:
                raise ValidationError("您的加入申请正在审核中")
            if existing["status"] == MemberStatus.REJECTED.value:
                # 允许重新申请
                self._repo.add_member(group_id, user_id, role=GroupRole.MEMBER.value, status=MemberStatus.PENDING.value)
                return
        self._repo.add_member(group_id, user_id, role=GroupRole.MEMBER.value, status=MemberStatus.PENDING.value)

    def approve_member(self, user: User, group_id: str, member_user_id: str) -> None:
        """审批通过小组成员申请"""
        group = self._repo.get(group_id)
        if not group:
            raise ValidationError("小组不存在")
        if user.role != Role.SUPER_ADMIN and group["owner_id"] != user.id:
            raise PermissionDenied("只有小组管理员可以审批成员")
        member = self._repo.get_member(group_id, member_user_id)
        if not member:
            raise ValidationError("该用户未申请加入小组")
        if member["status"] != MemberStatus.PENDING.value:
            raise ValidationError("该申请已处理")
        self._repo.update_member_status(group_id, member_user_id, MemberStatus.APPROVED.value)

    def reject_member(self, user: User, group_id: str, member_user_id: str) -> None:
        """拒绝小组成员申请"""
        group = self._repo.get(group_id)
        if not group:
            raise ValidationError("小组不存在")
        if user.role != Role.SUPER_ADMIN and group["owner_id"] != user.id:
            raise PermissionDenied("只有小组管理员可以审批成员")
        member = self._repo.get_member(group_id, member_user_id)
        if not member:
            raise ValidationError("该用户未申请加入小组")
        if member["status"] != MemberStatus.PENDING.value:
            raise ValidationError("该申请已处理")
        self._repo.update_member_status(group_id, member_user_id, MemberStatus.REJECTED.value)

    def remove_member(self, user: User, group_id: str, member_user_id: str) -> None:
        """移除成员"""
        group = self._repo.get(group_id)
        if not group:
            raise ValidationError("小组不存在")
        if user.role != Role.SUPER_ADMIN and group["owner_id"] != user.id:
            raise PermissionDenied("只有小组管理员可以移除成员")
        if member_user_id == group["owner_id"]:
            raise ValidationError("不能移除小组创建者")
        self._repo.remove_member(group_id, member_user_id)

    def list_members(self, group_id: str) -> list[dict]:
        return self._repo.list_members(group_id)

    def list_pending_applications(self, user: User) -> list[dict]:
        """管理员查看自己的小组中待审批的申请"""
        return self._repo.list_pending_applications(user.id)

    def get_user_pending_applications(self, user_id: str) -> list[dict]:
        """获取用户的所有待审批/已拒绝申请状态"""
        conn = self._repo  # type: ignore
        # 返回所有有申请记录的小组状态
        result = []
        all_groups = self._repo.list_all()
        for g in all_groups:
            member = self._repo.get_member(g["id"], user_id)
            if member:
                result.append({"group": g, "member": member})
        return result

    # ── 活动可见性 ─────────────────────────────────────────

    def list_accessible_activities(self, user_id: str) -> list[dict]:
        """获取用户可报名的活动：公开活动 + 用户所在小组的活动"""
        all_activities = self._activity_repo.list_all()
        user_group_ids = {g["id"] for g in self._repo.list_by_user(user_id)}

        accessible = []
        for activity in all_activities:
            group_id = activity.get("group_id")
            if group_id is None or group_id == "":
                # 公开活动
                accessible.append(activity)
            elif group_id in user_group_ids:
                # 用户是该小组成员
                accessible.append(activity)
        return accessible

    def can_access_activity(self, user_id: str, activity_id: str) -> bool:
        """检查用户是否有权限报名该活动"""
        activity = self._activity_repo.get(activity_id)
        if not activity:
            return False
        group_id = activity.get("group_id")
        if not group_id:
            return True  # 公开活动
        return self._repo.is_member(group_id, user_id)
