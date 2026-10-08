from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.errors import ApplicationError
from src.core.mapping import to_user, to_role
from src.core.models import AuditModel, RoleModel, UserModel


def snapshot(row):
    return {key: getattr(row, key) for key in ("id", "name", "lastname", "email", "phone", "role_id", "active")}


class MySQLUserRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, offset, limit):
        rows = self.session.scalars(select(UserModel).order_by(UserModel.created_at, UserModel.id)
                                    .offset(offset).limit(limit)).all()
        return [to_user(row) for row in rows]

    def _row(self, user_id):
        row = self.session.get(UserModel, user_id)
        if row is None:
            raise ApplicationError("User not found", 404)
        return row

    def get(self, user_id):
        return to_user(self._row(user_id))

    def _role(self, role_id):
        role = self.session.get(RoleModel, role_id)
        if role is None:
            raise ApplicationError("Role not found", 404)
        return role

    def get_role(self, role_id):
        return to_role(self._role(role_id))

    def create(self, values, actor_id):
        role = self._role(values["role_id"])
        row = UserModel(**values, role=role)
        self.session.add(row)
        self.session.flush()
        self.session.add(AuditModel(user_id=actor_id, table="users", record_id=row.id,
                                    action="INSERT", new_values=snapshot(row)))
        self.session.flush()
        return to_user(row)

    def update(self, user_id, values, actor_id):
        row = self._row(user_id)
        before = snapshot(row)
        if "role_id" in values:
            row.role = self._role(values["role_id"])
        for key, value in values.items():
            setattr(row, key, value)
        if any(key in values for key in ("password_hash", "role_id", "active")):
            row.token_version = UserModel.token_version + 1
        self.session.flush()
        after = snapshot(row)
        if "password_hash" in values:
            after["password_changed"] = True
        self.session.add(AuditModel(user_id=actor_id, table="users", record_id=row.id,
                                    action="UPDATE", old_values=before, new_values=after))
        self.session.flush()
        return to_user(row)
