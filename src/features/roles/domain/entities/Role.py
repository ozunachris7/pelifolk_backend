from dataclasses import dataclass

PERMISSIONS = frozenset({"users:read", "users:write", "roles:read", "roles:write",
                         "animals:read", "animals:write", "locations:read", "locations:write",
                         "groups:read", "groups:write", "weights:read", "weights:write", "health:read", "health:write", "breeding:read", "breeding:write", "exits:read", "exits:write", "finance:read", "finance:write"})
INITIAL_ROLES = ("owner", "administrator", "manager", "worker", "veterinarian", "livestock_technician")


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    is_system: bool
    permissions: tuple[str, ...]
