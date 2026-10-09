from src.features.roles.domain.entities.Role import Role
from src.features.users.domain.entities.User import User


def to_role(row):
    return Role(row.id, row.name, row.is_system, tuple(sorted(p.permission for p in row.permissions)))


def to_user(row):
    if row is None:
        return None
    return User(row.id, row.name, row.middle_name, row.paternal_lastname, row.maternal_lastname, row.email, row.phone, row.active,
                to_role(row.role), row.password_hash, row.token_version)
