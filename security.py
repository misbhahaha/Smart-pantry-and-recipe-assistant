from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="pantryflow-auth")


def create_access_token(user_id: int) -> str:
    return _serializer().dumps({"sub": user_id})


def decode_access_token(token: str) -> int:
    data = _serializer().loads(token, max_age=settings.access_token_max_age_seconds)
    return int(data["sub"])
