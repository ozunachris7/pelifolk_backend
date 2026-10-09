from src.core.errors import ApplicationError
from src.features.animals.domain.repository import AnimalRepository


class ManageAnimals:
    def __init__(self, repository: AnimalRepository):
        self.repository = repository

    def save(self, data, actor, animal_id=None):
        if 'animals:write' not in actor.role.permissions:
            raise ApplicationError('Insufficient permissions', 403)
        return self.repository.save(data, actor.id, animal_id)
