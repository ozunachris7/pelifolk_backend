from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    paternal_lastname: str = Field(min_length=1, max_length=120)
    maternal_lastname: str = Field(default=None, min_length=1, max_length=120)
    email: EmailStr = Field(max_length=190)
    password: str = Field(min_length=12, max_length=128)
    role_id: UUID
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("name", "paternal_lastname", "maternal_lastname", "email", mode="before")
    @classmethod
    def clean(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            return value.lower() if info.field_name == "email" else value
        return value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    paternal_lastname: str | None = Field(default=None, min_length=1, max_length=120)
    maternal_lastname: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = Field(default=None, max_length=190)
    password: str | None = Field(default=None, min_length=12, max_length=128)
    role_id: UUID | None = None
    phone: str | None = Field(default=None, max_length=30)
    active: bool | None = None
    clean = field_validator("name", "paternal_lastname", "maternal_lastname", "email", mode="before")(UserCreate.clean.__func__)

    @model_validator(mode="after")
    def reject_null_fields(self):
        for name in self.model_fields_set - {"phone"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class UserResponse(BaseModel):
    id: str
    name: str
    paternal_lastname: str
    maternal_lastname: str | None
    email: str
    phone: str | None
    active: bool
    role_id: str
    role_name: str
    permissions: list[str]

    @classmethod
    def from_user(cls, user):
        return cls(id=user.id, name=user.name, paternal_lastname=user.paternal_lastname, maternal_lastname=user.maternal_lastname, email=user.email,
                   phone=user.phone, active=user.active, role_id=user.role.id,
                   role_name=user.role.name, permissions=list(user.role.permissions))