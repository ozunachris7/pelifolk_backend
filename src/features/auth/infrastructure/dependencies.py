from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.security import DUMMY_HASH, issue_token, read_token, verify_password
from src.features.auth.application.LoginUseCase import LoginUseCase
from src.features.auth.infrastructure.adapters.MySQL import MySQLAuthRepository

bearer = HTTPBearer(auto_error=False)


def get_auth_repository(db: Session = Depends(get_db, scope="function")):
    return MySQLAuthRepository(db)


def get_login_use_case(repository=Depends(get_auth_repository)):
    return LoginUseCase(repository, verify_password, issue_token, DUMMY_HASH)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 repository=Depends(get_auth_repository)):
    if credentials is None:
        raise ApplicationError("Authentication required", 401)
    claims = read_token(credentials.credentials)
    user = repository.find_by_id(claims["sub"])
    if not user or not user.active or user.token_version != claims["ver"]:
        raise ApplicationError("Invalid or expired access token", 401)
    return user


def require_permission(permission: str):
    def dependency(user=Depends(current_user)):
        missing_health_read = (
            permission.startswith('health:')
            and permission != 'health:read'
            and 'health:read' not in user.role.permissions
        )
        if permission not in user.role.permissions or missing_health_read:
            raise ApplicationError("Insufficient permissions", 403)
        return user
    return dependency
