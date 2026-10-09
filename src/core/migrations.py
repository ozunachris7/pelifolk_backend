"""Ordered MySQL SQL migrations, serialized across API workers."""

from hashlib import sha256
import logging
from pathlib import Path
import re

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"
logger = logging.getLogger(__name__)


def split_sql(source: str) -> list[str]:
    """Read SQL and mysql-client DELIMITER directives without splitting routines."""
    delimiter = ";"
    statements: list[str] = []
    buffer: list[str] = []
    quote = None
    block_comment = False
    for line in source.splitlines(keepends=True):
        directive = re.fullmatch(r"\s*DELIMITER\s+(\S+)\s*", line, re.IGNORECASE)
        if directive and quote is None and not block_comment:
            if "".join(buffer).strip():
                raise ValueError("DELIMITER changed before a statement was terminated")
            buffer.clear()
            delimiter = directive[1]
            continue
        i = 0
        while i < len(line):
            ch = line[i]
            if block_comment:
                if line.startswith("*/", i):
                    block_comment = False
                    i += 2
                    buffer.append(" ")
                else:
                    i += 1
                continue
            if quote:
                buffer.append(ch)
                if ch == "\\" and i + 1 < len(line):
                    i += 1
                    buffer.append(line[i])
                elif ch == quote:
                    if i + 1 < len(line) and line[i + 1] == quote:
                        i += 1
                        buffer.append(line[i])
                    else:
                        quote = None
                i += 1
                continue
            if ch == "#" or (line.startswith("--", i) and
                             (i + 2 == len(line) or line[i + 2].isspace())):
                buffer.append("\n")
                break
            if line.startswith("/*", i):
                block_comment = True
                i += 2
                continue
            if line.startswith(delimiter, i):
                statement = "".join(buffer).strip()
                if statement:
                    statements.append(statement)
                buffer.clear()
                i += len(delimiter)
                continue
            if ch in "'\"`":
                quote = ch
            buffer.append(ch)
            i += 1
    if quote or block_comment or "".join(buffer).strip():
        raise ValueError("Unterminated SQL statement, quote or comment")
    return statements


def _routine_exists(connection: Connection, statement: str) -> bool:
    match = re.match(r"CREATE\s+(FUNCTION|PROCEDURE|TRIGGER)\s+(\w+)", statement, re.I)
    if not match:
        return False
    kind, name = match.groups()
    if kind.upper() == "TRIGGER":
        sql = ("SELECT COUNT(*) FROM information_schema.TRIGGERS "
               "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = :name")
        params = {"name": name}
    else:
        sql = ("SELECT COUNT(*) FROM information_schema.ROUTINES "
               "WHERE ROUTINE_SCHEMA = DATABASE() AND ROUTINE_NAME = :name "
               "AND ROUTINE_TYPE = :kind")
        params = {"name": name, "kind": kind.upper()}
    return bool(connection.execute(text(sql), params).scalar())


def _apply_migration(connection: Connection, path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    checksum = sha256(source.encode()).hexdigest()
    version = path.stem
    row = connection.execute(text(
        "SELECT checksum, completed_steps, applied_at FROM schema_migrations "
        "WHERE version = :version"), {"version": version}).mappings().first()
    if row and row["checksum"] != checksum:
        raise RuntimeError(f"Applied or started migration {version} has been modified")
    if row and row["applied_at"] is not None:
        return
    statements = split_sql(source)
    if not row:
        connection.execute(text(
            "INSERT INTO schema_migrations (version, checksum, completed_steps) "
            "VALUES (:version, :checksum, 0)"), {"version": version, "checksum": checksum})
        connection.commit()
    completed = row["completed_steps"] if row else 0
    for index, statement in enumerate(statements[completed:], start=completed + 1):
        try:
            # A DDL statement may have committed before its progress was saved.
            # Initial tables/seeds are retryable; routines are checked explicitly.
            if not _routine_exists(connection, statement):
                connection.exec_driver_sql(statement)
            connection.execute(text(
                "UPDATE schema_migrations SET completed_steps = :steps WHERE version = :version"
            ), {"steps": index, "version": version})
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise RuntimeError(
                f"Migration {version} failed at statement {index}; "
                "fix the database permissions or reported SQL error before restarting"
            ) from exc
    connection.execute(text(
        "UPDATE schema_migrations SET applied_at = CURRENT_TIMESTAMP WHERE version = :version"
    ), {"version": version})
    connection.commit()
    logger.info("Applied database migration %s", version)


def run_migrations(engine: Engine, directory: Path = MIGRATIONS_DIR) -> None:
    if engine.dialect.name != "mysql":
        raise RuntimeError("Automatic migrations require MySQL")
    paths = sorted(directory.glob("[0-9]*.sql"))
    if not paths:
        raise RuntimeError("No database migrations found")
    with engine.connect() as connection:
        database = connection.execute(text("SELECT DATABASE()")).scalar()
        if not database:
            raise RuntimeError("DATABASE_URL must select an existing database")
        # Advisory locks stay held through MySQL's implicit DDL commits.
        lock = "pelifolk:" + sha256(database.encode()).hexdigest()[:48]
        acquired = connection.execute(text("SELECT GET_LOCK(:name, 30)"), {"name": lock}).scalar()
        if acquired != 1:
            raise RuntimeError("Could not acquire the database migration lock")
        try:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            if "schema_migrations" not in tables and (tables or inspector.get_view_names()):
                raise RuntimeError(
                    "The database contains an unversioned schema. Automatic initialization "
                    "requires an empty database; existing data needs an explicit migration. "
                    "No existing tables were changed."
                )
            connection.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(120) PRIMARY KEY,
                    checksum CHAR(64) NOT NULL,
                    completed_steps INT UNSIGNED NOT NULL DEFAULT 0,
                    applied_at TIMESTAMP NULL DEFAULT NULL
                )
            """)
            connection.commit()
            known = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
            missing = known - {path.stem for path in paths}
            if missing:
                raise RuntimeError("The database has migrations missing from this application")
            for path in paths:
                _apply_migration(connection, path)
        finally:
            connection.rollback()
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock})
            connection.commit()
