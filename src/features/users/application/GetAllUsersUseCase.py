class GetAllUsersUseCase:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, offset=0, limit=50, exclude_user_id=None):
        return self.repository.list(offset, limit, exclude_user_id)
