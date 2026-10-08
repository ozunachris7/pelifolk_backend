from src.core.errors import ApplicationError


class DeleteUserUseCase:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, user_id, actor):
        if user_id == actor.id:
            raise ApplicationError("You cannot deactivate your own account", 409)
        target = self.repository.get(user_id)
        if not set(target.role.permissions).issubset(actor.role.permissions):
            raise ApplicationError("Cannot modify a user with higher permissions", 403)
        self.repository.update(user_id, {"active": False}, actor.id)
