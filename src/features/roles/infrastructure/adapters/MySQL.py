from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.errors import ApplicationError
from src.core.mapping import to_role
from src.core.models import AuditModel, RoleModel, RolePermissionModel, UserModel


def snapshot(row):
    return {"name": row.name, "permissions": sorted(p.permission for p in row.permissions)}


class MySQLRoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self):
        return [to_role(row) for row in self.session.scalars(select(RoleModel).order_by(RoleModel.name))]

    def get(self, role_id):
        row = self.session.get(RoleModel, role_id)
        if row is None:
            raise ApplicationError("Role not found", 404)
        return to_role(row)

    def create(self, name, permissions, actor_id):
        row = RoleModel(name=name, permissions=[RolePermissionModel(permission=p) for p in permissions])
        self.session.add(row)
        self.session.flush()
        self._audit(row, actor_id, "INSERT", None, snapshot(row))
        return to_role(row)

    def _locked(self, role_id):
        row = self.session.scalar(select(RoleModel).where(RoleModel.id == role_id).with_for_update())
        if row is None:
            raise ApplicationError("Role not found", 404)
        return row

    def update(self, role_id, name, permissions, actor_id):
        row = self._locked(role_id)
        if row.is_system and row.name == "owner":
            raise ApplicationError("Owner role cannot be modified", 409)
        if row.is_system and name != row.name:
            raise ApplicationError("Initial system role names cannot be changed", 409)
        before = snapshot(row)
        # A manager cannot remove their own access by editing their assigned role.
        actor = self.session.get(UserModel, actor_id)
        if actor and actor.role_id == role_id:
            raise ApplicationError("You cannot modify your own assigned role", 409)
        row.name = name
        wanted = set(permissions)
        existing = {p.permission for p in row.permissions}
        row.permissions[:] = [p for p in row.permissions if p.permission in wanted]
        row.permissions.extend(RolePermissionModel(permission=p) for p in wanted - existing)
        self.session.flush()
        self._audit(row, actor_id, "UPDATE", before, snapshot(row))
        return to_role(row)

    def delete(self, role_id, actor_id):
        row = self._locked(role_id)
        if row.is_system:
            raise ApplicationError("Initial system roles cannot be deleted", 409)
        if self.session.scalar(select(UserModel.id).where(UserModel.role_id == role_id).limit(1)):
            raise ApplicationError("Role is assigned to users", 409)
        self._audit(row, actor_id, "DELETE", snapshot(row), None)
        self.session.delete(row)
        self.session.flush()

    def _audit(self, row, actor_id, action, before, after):
        self.session.add(AuditModel(user_id=actor_id, table="roles", record_id=row.id,
                                    action=action, old_values=before, new_values=after))
        self.session.flush()
