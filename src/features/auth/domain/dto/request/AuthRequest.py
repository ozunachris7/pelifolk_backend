from pydantic import BaseModel, EmailStr, Field, field_validator


class AuthRequest(BaseModel):
    email: EmailStr = Field(max_length=190)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value
