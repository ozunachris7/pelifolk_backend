from dataclasses import dataclass

PERMISSIONS = frozenset({"audit:read", "history:rectify", "users:read", "users:write", "roles:read", "roles:write",
                         "animals:read", "animals:write", "locations:read", "locations:write",
                         "groups:read", "groups:write", "weights:read", "weights:write", "health:read", "breeding:read", "breeding:write", "exits:read", "exits:write", "finance:read", "finance:write", "feeding:read", "feeding:write"})
HEALTH_ACTIONS = frozenset({
    'health:cases:write',
    'health:diagnoses:create',
    'health:doses:create',
    'health:followups:create',
    'health:incidents:write',
    'health:observations:create',
    'health:products:write',
    'health:program_applications:create',
    'health:programs:write',
    'health:reactions:write',
    'health:treatments:create',
})
PERMISSIONS = PERMISSIONS | HEALTH_ACTIONS
INITIAL_ROLES = ("owner", "administrator", "manager", "worker", "veterinarian", "livestock_technician")


@dataclass(frozen=True)
class Role:
    id: str
    name: str
    is_system: bool
    permissions: tuple[str, ...]
