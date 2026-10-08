from pydantic import BaseModel
from src.features.users.domain.dto.UserDTO import UserResponse


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
