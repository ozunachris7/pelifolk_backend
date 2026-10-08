from dataclasses import dataclass
from src.features.roles.domain.entities.Role import Role


@dataclass(frozen=True)
class User:
    id: str
    name: str
    paternal_lastname: str
    maternal_lastname: str | None
    email: str
    phone: str | None
    active: bool
    role: Role
    password_hash: str
    token_version: int
