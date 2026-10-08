from src.features.auth.domain.dto.response.AuthResponse import AuthResponse
from src.features.users.domain.dto.UserDTO import UserResponse


class LoginController:
    @staticmethod
    def execute(request, use_case):
        result = use_case.execute(str(request.email), request.password)
        return AuthResponse(access_token=result.access_token, expires_in=result.expires_in,
                            user=UserResponse.from_user(result.user))
