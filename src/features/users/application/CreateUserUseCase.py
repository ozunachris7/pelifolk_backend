from src.core.errors import ApplicationError
from src.features.users.domain.UserRepository import UserRepository


class CreateUserUseCase:
    def __init__(self, repository: UserRepository, hash_password):
        self.repository, self.hash_password = repository, hash_password

    def execute(self, values: dict, actor):
        values = dict(values)
        role = self.repository.get_role(values["role_id"])
        if not set(role.permissions).issubset(actor.role.permissions):
            raise ApplicationError("Cannot assign permissions you do not have", 403)
        values["password_hash"] = self.hash_password(values.pop("password"))
        return self.repository.create(values, actor.id)
