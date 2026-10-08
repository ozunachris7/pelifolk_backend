from sqlalchemy import select, update
from sqlalchemy.orm import Session
from src.core.mapping import to_user
from src.core.models import UserModel


class MySQLAuthRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_email(self, email):
        return to_user(self.session.scalar(select(UserModel).where(UserModel.email == email)))

    def find_by_id(self, user_id):
        return to_user(self.session.get(UserModel, user_id))

    def revoke_sessions(self, user_id):
        self.session.execute(update(UserModel).where(UserModel.id == user_id).values(
            token_version=UserModel.token_version + 1))
        self.session.flush()
