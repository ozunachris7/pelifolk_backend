from dataclasses import dataclass
from src.features.users.domain.entities.User import User


@dataclass(frozen=True)
class Auth:
    access_token: str
    expires_in: int
    user: User
