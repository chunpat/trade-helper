from datetime import datetime, timedelta
from typing import Optional
import os
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

# password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# JWT
SECRET_KEY = os.getenv("JWT_SECRET", os.getenv("SECRET_KEY", "dev-secret-key"))
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _utcnow() -> datetime:
    return datetime.utcnow()


def _build_token_payload(data: dict, token_type: str, expires_delta: timedelta) -> tuple[dict, datetime]:
    issued_at = _utcnow()
    expire = issued_at + expires_delta
    payload = data.copy()
    payload.update(
        {
            "type": token_type,
            "iat": int(issued_at.timestamp()),
            "exp": expire,
            "jti": uuid4().hex,
        }
    )
    return payload, expire


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    effective_delta = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode, expire = _build_token_payload(data, ACCESS_TOKEN_TYPE, effective_delta)
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    effective_delta = expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode, expire = _build_token_payload(data, REFRESH_TOKEN_TYPE, effective_delta)
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire, to_encode["jti"]

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise


def get_token_type(payload: dict) -> Optional[str]:
    token_type = payload.get("type")
    if isinstance(token_type, str):
        return token_type
    return None


def get_token_jti(payload: dict) -> Optional[str]:
    token_jti = payload.get("jti")
    if isinstance(token_jti, str):
        return token_jti
    return None


def get_token_subject(payload: dict) -> Optional[str]:
    subject = payload.get("sub")
    if isinstance(subject, str):
        return subject
    return None
