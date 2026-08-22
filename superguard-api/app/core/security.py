"""
SuperGuard API - Security & Authentication
JWT RS256 token generation, password hashing, RBAC.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pathlib import Path

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(plain: str) -> str:
    return pwd_context.hash(plain)


def _load_key(path: str, is_private: bool = True) -> Optional[str]:
    p = Path(path)
    if p.exists():
        return p.read_text()
    return None


def create_access_token(
    subject: str,
    user_id: str,
    roles: List[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": subject,
        "uid": user_id,
        "roles": roles,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    private_key = _load_key(settings.jwt_private_key_path)
    if not private_key:
        raise RuntimeError("RSA private key not found at JWT_PRIVATE_KEY_PATH. Generate keys first.")
    return jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "uid": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    private_key = _load_key(settings.jwt_private_key_path)
    if not private_key:
        raise RuntimeError("RSA private key not found at JWT_PRIVATE_KEY_PATH. Generate keys first.")
    return jwt.encode(payload, private_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        public_key = _load_key(settings.jwt_public_key_path)
        if not public_key:
            raise RuntimeError("RSA public key not found at JWT_PUBLIC_KEY_PATH. Generate keys first.")
        return jwt.decode(token, public_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None