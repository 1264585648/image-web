from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

security = HTTPBearer(auto_error=False)
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if not EMAIL_PATTERN.match(value):
        raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")
    return value


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码至少需要 8 位")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="密码长度不能超过 128 位")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS)
    return "$".join([
        PASSWORD_HASH_ALGORITHM,
        str(PASSWORD_HASH_ITERATIONS),
        _b64encode(salt),
        _b64encode(digest),
    ])


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected_digest = _b64decode(digest_text)
        actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual_digest, expected_digest)
    except Exception:
        return False


def _sign(message: str) -> str:
    settings = get_settings()
    secret = settings.auth_secret.encode("utf-8")
    return _b64encode(hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest())


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time() + settings.auth_token_expire_hours * 3600),
    }
    payload_text = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _sign(payload_text)
    return f"{payload_text}.{signature}"


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        payload_text, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录") from exc

    expected_signature = _sign(payload_text)
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录")

    try:
        payload = json.loads(_b64decode(payload_text))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    if not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效，请重新登录")
    return payload


def create_resource_signature(kind: str, resource_id: str, *, expires_in_seconds: int | None = None) -> tuple[int, str]:
    settings = get_settings()
    expires_in = expires_in_seconds or settings.asset_url_expire_seconds
    expires = int(time.time()) + int(expires_in)
    message = f"{kind}:{resource_id}:{expires}"
    return expires, _sign(message)


def verify_resource_signature(kind: str, resource_id: str, expires: int, signature: str) -> None:
    if expires < int(time.time()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="图片链接已过期，请刷新页面后重试")
    expected_signature = _sign(f"{kind}:{resource_id}:{expires}")
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="图片链接无效")


def check_login_rate_limit(email: str, client_ip: str) -> None:
    settings = get_settings()
    now = time.time()
    window = settings.login_rate_limit_window_seconds
    max_attempts = settings.login_rate_limit_max_attempts
    keys = [f"email:{email}", f"ip:{client_ip or 'unknown'}"]
    for key in keys:
        attempts = [timestamp for timestamp in _login_attempts[key] if now - timestamp <= window]
        _login_attempts[key] = attempts
        if len(attempts) >= max_attempts:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="登录尝试过于频繁，请稍后再试")


def record_failed_login(email: str, client_ip: str) -> None:
    now = time.time()
    _login_attempts[f"email:{email}"].append(now)
    _login_attempts[f"ip:{client_ip or 'unknown'}"].append(now)


def clear_login_attempts(email: str, client_ip: str) -> None:
    _login_attempts.pop(f"email:{email}", None)
    _login_attempts.pop(f"ip:{client_ip or 'unknown'}", None)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    payload = verify_access_token(credentials.credentials)
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    return user
