from datetime import datetime, timedelta, timezone
from uuid import uuid4
import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from src.core.config import get_settings
from src.core.errors import ApplicationError

PASSWORD_HASHER = PasswordHash.recommended()
DUMMY_HASH = PASSWORD_HASHER.hash(str(uuid4()))


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password, encoded)
    except (ValueError, TypeError, PwdlibError):
        return False


def issue_token(user_id: str, version: int) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    seconds = settings.access_token_minutes * 60
    claims = {"sub": user_id, "ver": version, "iat": now, "exp": now + timedelta(seconds=seconds),
              "iss": settings.jwt_issuer, "aud": "pelifolk", "jti": str(uuid4()), "type": "access"}
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256"), seconds


def read_token(token: str) -> dict:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
                            issuer=settings.jwt_issuer, audience="pelifolk",
                            options={"require": ["sub", "exp", "iat", "iss", "aud", "ver", "type"]})
        if claims["type"] != "access" or not isinstance(claims["ver"], int):
            raise jwt.InvalidTokenError()
        return claims
    except jwt.InvalidTokenError:
        raise ApplicationError("Invalid or expired access token", 401)
