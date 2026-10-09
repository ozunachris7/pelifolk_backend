"""Create the first owner interactively with both required surnames."""
import argparse
import getpass
from sqlalchemy import select
from src.core.database import get_session_factory
from src.core.models import AuditModel, RoleModel, UserModel
from src.core.security import hash_password
from src.features.users.domain.dto.UserDTO import UserCreate
from src.features.users.infrastructure.adapters.MySQL import snapshot


def main():
    parser = argparse.ArgumentParser(description="Create the first owner; both surnames are required.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--middle-name")
    parser.add_argument("--phone")
    parser.add_argument("--paternal-lastname", required=True)
    parser.add_argument("--maternal-lastname", required=True)
    args = parser.parse_args()
    with get_session_factory()() as session, session.begin():
        role = session.scalar(select(RoleModel).where(RoleModel.name == "owner").with_for_update())
        if role is None:
            raise SystemExit("Apply the SQL schema and role seed first")
        if session.scalar(select(UserModel.id).limit(1)):
            raise SystemExit("Bootstrap is only available before the first user; use the protected API")
        password = getpass.getpass("Password (minimum 8 characters): ")
        if password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        data = UserCreate(name=args.name, middle_name=args.middle_name, paternal_lastname=args.paternal_lastname,
                          maternal_lastname=args.maternal_lastname, email=args.email, phone=args.phone,
                          password=password, role_id=role.id)
        values = data.model_dump(exclude={"password"})
        values["role_id"] = str(values["role_id"])
        values["password_hash"] = hash_password(password)
        row = UserModel(**values)
        session.add(row)
        session.flush()
        session.add(AuditModel(user_id=row.id, table="users", record_id=row.id,
                              action="INSERT", new_values=snapshot(row)))
    print("Owner created. Sign in at /api/v1/auth/login.")


if __name__ == "__main__":
    main()
