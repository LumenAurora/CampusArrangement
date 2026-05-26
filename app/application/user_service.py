from __future__ import annotations

from app.domain.exceptions import ValidationError
from app.domain.models import Role, User
from app.infrastructure.auth import verify_password, hash_password
from app.infrastructure.repositories import UserRepository


class UserService:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def register(self, username: str, password: str, role: Role) -> User:
        if not username or not password:
            raise ValidationError("用户名和密码不能为空")
        if self._user_repo.get_by_username(username):
            raise ValidationError("用户名已存在")
        user = User.create(username=username, role=role)
        self._user_repo.create(user, hash_password(password))
        return user

    def authenticate(self, username: str, password: str) -> User:
        record = self._user_repo.get_by_username(username)
        if not record or not verify_password(password, record["password_hash"]):
            raise ValidationError("用户名或密码错误")
        return User(id=record["id"], username=record["username"], role=Role(record["role"]))
