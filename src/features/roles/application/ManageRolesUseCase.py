from src.core.errors import ApplicationError
from src.features.roles.domain.RoleRepository import RoleRepository


class ManageRolesUseCase:
    def __init__(self, repository: RoleRepository):
        self.repository = repository

    def list(self):
        return self.repository.list()

    def _allowed(self, permissions, actor):
        if not set(permissions).issubset(actor.role.permissions):
            raise ApplicationError("Cannot grant or manage permissions you do not have", 403)

    def create(self, name, permissions, actor):
        self._allowed(permissions, actor)
        return self.repository.create(name, permissions, actor.id)

    def update(self, role_id, name, permissions, actor):
        self._allowed(self.repository.get(role_id).permissions, actor)
        self._allowed(permissions, actor)
        return self.repository.update(role_id, name, permissions, actor.id)

    def delete(self, role_id, actor):
        self._allowed(self.repository.get(role_id).permissions, actor)
        self.repository.delete(role_id, actor.id)
