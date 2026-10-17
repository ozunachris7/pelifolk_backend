import re
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.features.roles.domain.entities.Role import PERMISSIONS, HEALTH_ACTIONS


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=60)
    permissions: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        if isinstance(value, str):
            value = value.strip().lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,59}", value):
                raise ValueError("Use a lowercase role name with letters, digits and underscores")
        return value

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value):
        if set(value) - PERMISSIONS:
            raise ValueError("Unknown permission")
        if set(value) & HEALTH_ACTIONS and 'health:read' not in value:
            raise ValueError('Health actions require health:read')
        return sorted(set(value))


class RoleResponse(BaseModel):
    id: str
    name: str
    is_system: bool
    permissions: list[str]

    @classmethod
    def from_role(cls, role):
        return cls(id=role.id, name=role.name, is_system=role.is_system, permissions=list(role.permissions))
