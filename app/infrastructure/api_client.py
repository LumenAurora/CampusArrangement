from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import requests

from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import NotificationMode, Role, User, UserStatus


def is_loopback_api_url(base_url: str) -> bool:
    host = urlparse(base_url).hostname
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if is_loopback_api_url(self._base_url):
            self._session.trust_env = False
        self._token: str | None = None

    def set_token(self, token: str) -> None:
        self._token = token

    def login(self, username: str, password: str) -> User:
        payload = self._request(
            "POST",
            "/auth/login",
            json={"username": username, "password": password},
            require_auth=False,
        )
        token = payload.get("token")
        user = payload.get("user", {})
        if token:
            self.set_token(token)
        return User(
            id=user["id"],
            username=user["username"],
            role=Role(user["role"]),
            status=UserStatus(user.get("status", "approved")),
            avatar_path=user.get("avatar_path", ""),
            notification_mode=NotificationMode(user.get("notification_mode", "in_app")),
        )

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, require_auth: bool = True) -> Any:
        return self._request("POST", path, json=json, require_auth=require_auth)

    def put(self, path: str, json: dict | None = None, require_auth: bool = True) -> Any:
        return self._request("PUT", path, json=json, require_auth=require_auth)

    def delete(self, path: str, json: dict | None = None, require_auth: bool = True) -> Any:
        return self._request("DELETE", path, json=json, require_auth=require_auth)

    def post_file(self, path: str, field_name: str, file_path: str, require_auth: bool = True) -> Any:
        try:
            fh = open(file_path, "rb")
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise ValueError(f"无法读取文件 {file_path}: {exc}") from exc
        with fh:
            return self._request("POST", path, files={field_name: fh}, require_auth=require_auth)

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        require_auth: bool = True,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {}
        if require_auth:
            if not self._token:
                raise ValidationError("尚未登录服务端")
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            response = self._session.request(
                method,
                url,
                json=json,
                params=params,
                files=files,
                headers=headers,
                timeout=8,
            )
        except requests.RequestException as exc:
            raise ValidationError("无法连接服务端，请检查地址与网络") from exc
        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("detail", "")
            except ValueError:
                detail = response.text
            detail = detail or "服务端返回错误"
            if response.status_code == 401:
                self._token = None
                raise ValidationError(f"认证已过期，请重新登录：{detail}")
            if response.status_code == 403:
                raise PermissionDenied(detail)
            if response.status_code == 404:
                raise ValidationError(f"资源不存在：{detail}")
            if response.status_code == 409:
                raise ConflictError(detail)
            if response.status_code >= 500:
                raise ValidationError(f"服务器内部错误：{detail}")
            raise ValidationError(detail)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ValidationError("服务端响应格式错误") from exc
