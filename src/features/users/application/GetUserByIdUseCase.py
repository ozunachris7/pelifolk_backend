class GetUserByIdUseCase:
    def __init__(self, repository):
        self.repository = repository

    def execute(self, user_id):
        return self.repository.get(user_id)
