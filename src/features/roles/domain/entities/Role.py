from dataclasses import dataclass

PERMISSIONS = frozenset({"users:read", "users:write", "roles:read", "roles:write"})
INITIAL_ROLES = ("owner", "administrator", "manager", "worker", "veterinarian", "livestock_technician")


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    is_system: bool
    permissions: tuple[str, ...]
