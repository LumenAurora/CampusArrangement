from __future__ import annotations

from typing import Any

import requests

from app.domain.exceptions import ConflictError, PermissionDenied, ValidationError
from app.domain.models import Role, User, UserStatus


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
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
        return User(id=user["id"], username=user["username"], role=Role(user["role"]),
                    status=UserStatus(user.get("status", "approved")))

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None, require_auth: bool = True) -> Any:
        return self._request("POST", path, json=json, require_auth=require_auth)

    def put(self, path: str, json: dict | None = None, require_auth: bool = True) -> Any:
        return self._request("PUT", path, json=json, require_auth=require_auth)

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
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
            if response.status_code == 403:
                raise PermissionDenied(detail)
            if response.status_code == 409:
                raise ConflictError(detail)
            raise ValidationError(detail)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ValidationError("服务端响应格式错误") from exc
