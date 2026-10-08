from src.core.errors import ApplicationError


class UpdateUserUseCase:
    def __init__(self, repository, hash_password):
        self.repository, self.hash_password = repository, hash_password

    def execute(self, user_id, values, actor):
        values = dict(values)
        if user_id == actor.id and ("role_id" in values or values.get("active") is False):
            raise ApplicationError("You cannot change your own role or deactivate your own account", 409)
        target = self.repository.get(user_id)
        if not set(target.role.permissions).issubset(actor.role.permissions):
            raise ApplicationError("Cannot modify a user with higher permissions", 403)
        if "role_id" in values:
            role = self.repository.get_role(values["role_id"])
            if not set(role.permissions).issubset(actor.role.permissions):
                raise ApplicationError("Cannot assign permissions you do not have", 403)
        if "password" in values:
            values["password_hash"] = self.hash_password(values.pop("password"))
        return self.repository.update(user_id, values, actor.id)
