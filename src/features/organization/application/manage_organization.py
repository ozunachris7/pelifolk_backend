from src.core.errors import ApplicationError
from src.features.organization.domain.repository import OrganizationRepository


class ManageOrganization:
    def __init__(self, repository: OrganizationRepository):
        self.repository = repository

    def assign(self, group_id, data, actor):
        if 'groups:write' not in actor.role.permissions:
            raise ApplicationError('Insufficient permissions', 403)
        return self.repository.assign(group_id, data, actor.id)

    def remove(self, group_id, animal_id, data, actor):
        if 'groups:write' not in actor.role.permissions:
            raise ApplicationError('Insufficient permissions', 403)
        return self.repository.remove(group_id, animal_id, data.effective_date, actor.id)
