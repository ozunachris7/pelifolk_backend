from typing import Callable
from src.core.errors import ApplicationError
from src.features.auth.domain.AuthRepository import AuthRepository
from src.features.auth.domain.entities.Auth import Auth


class LoginUseCase:
    def __init__(self, repository: AuthRepository, verify: Callable, issue: Callable, dummy_hash: str):
        self.repository, self.verify, self.issue, self.dummy_hash = repository, verify, issue, dummy_hash

    def execute(self, email: str, password: str) -> Auth:
        user = self.repository.find_by_email(email.strip().lower())
        valid = self.verify(password, user.password_hash if user else self.dummy_hash)
        if not user or not valid or not user.active:
            raise ApplicationError("Invalid email or password", 401)
        token, expires = self.issue(user.id, user.token_version)
        return Auth(token, expires, user)
