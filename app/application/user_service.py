from __future__ import annotations

from app.domain.exceptions import PermissionDenied, ValidationError
from app.domain.models import Role, User, UserStatus
from app.infrastructure.auth import verify_password, hash_password
from app.infrastructure.repositories import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def register(self, current_user: User | None, username: str, password: str, role: Role) -> User:
        # 权限检查（current_user 为 None 时跳过，用于初始化管理员）
        if current_user is not None:
            if current_user.role == Role.USER:
                raise PermissionDenied("普通用户无权创建用户")
            if current_user.role == Role.ORGANIZER and role != Role.USER:
                raise PermissionDenied("组织者只能创建普通用户")

        if not username or not username.strip():
            raise ValidationError("用户名不能为空")
        if not password or len(password) < 4:
            raise ValidationError("密码长度不能少于4位")
        if self._user_repo.get_by_username(username.strip()):
            raise ValidationError("用户名已存在")
        user = User.create(username=username.strip(), role=role)
        self._user_repo.create(user, hash_password(password))
        return user

    def self_register(self, username: str, password: str) -> User:
        """用户自助注册，注册后状态为待审批"""
        if not username or not username.strip():
            raise ValidationError("用户名不能为空")
        if not password or len(password) < 4:
            raise ValidationError("密码长度不能少于4位")
        if self._user_repo.get_by_username(username.strip()):
            raise ValidationError("用户名已存在")
        user = User.create(username=username.strip(), role=Role.USER, status=UserStatus.PENDING_REVIEW)
        self._user_repo.create(user, hash_password(password))
        return user

    def approve_user(self, current_user: User, user_id: str) -> User:
        """审批通过用户注册"""
        if current_user.role == Role.USER:
            raise PermissionDenied("普通用户无权审批用户")
        record = self._user_repo.get_by_id(user_id)
        if not record:
            raise ValidationError("用户不存在")
        if record.get("status") != UserStatus.PENDING_REVIEW.value:
            raise ValidationError("该用户不在待审批状态")
        self._user_repo.update_status(user_id, UserStatus.APPROVED)
        return User(id=record["id"], username=record["username"], role=Role(record["role"]), status=UserStatus.APPROVED)

    def reject_user(self, current_user: User, user_id: str) -> None:
        """拒绝用户注册"""
        if current_user.role == Role.USER:
            raise PermissionDenied("普通用户无权审批用户")
        record = self._user_repo.get_by_id(user_id)
        if not record:
            raise ValidationError("用户不存在")
        if record.get("status") != UserStatus.PENDING_REVIEW.value:
            raise ValidationError("该用户不在待审批状态")
        self._user_repo.update_status(user_id, UserStatus.REJECTED)

    def list_pending_users(self, current_user: User) -> list[dict]:
        """获取待审批用户列表"""
        if current_user.role == Role.USER:
            raise PermissionDenied("普通用户无权查看待审批用户")
        return self._user_repo.list_by_status(UserStatus.PENDING_REVIEW)

    def authenticate(self, username: str, password: str) -> User:
        record = self._user_repo.get_by_username(username)
        if not record or not verify_password(password, record["password_hash"]):
            raise ValidationError("用户名或密码错误")
        status = UserStatus(record.get("status", "approved"))
        if status == UserStatus.PENDING_REVIEW:
            raise ValidationError("账号待审批，请等待管理员审核")
        if status == UserStatus.REJECTED:
            raise ValidationError("账号已被拒绝，请联系管理员")
        return User(id=record["id"], username=record["username"], role=Role(record["role"]), status=status)

    def delete_user(self, current_user: User, user_id: str) -> bool:
        if current_user.role != Role.SUPER_ADMIN:
            raise PermissionDenied("仅超级管理员可删除用户")
        if current_user.id == user_id:
            raise ValidationError("不能删除自己")
        user = self._user_repo.get_by_id(user_id)
        if not user:
            raise ValidationError("用户不存在")
        return self._user_repo.delete(user_id)

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        """用户修改自己的密码"""
        if not new_password or len(new_password) < 4:
            raise ValidationError("新密码长度不能少于4位")

        record = self._user_repo.get_by_id(user.id)
        if not record:
            raise ValidationError("用户不存在")

        if not verify_password(old_password, record["password_hash"]):
            raise ValidationError("原密码不正确")

        self._user_repo.update_password(user.id, hash_password(new_password))
