import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from src.core.migrations import MIGRATIONS_DIR, run_migrations, split_sql


def test_sql_parser_preserves_routines_and_quoted_delimiters():
    source = """
    -- comment ;
    CREATE TABLE example (value VARCHAR(100));
    INSERT INTO example VALUES ('a; b'), ('it''s; quoted'); /* ; */
    DELIMITER $$
    CREATE FUNCTION example_fn() RETURNS INT
    BEGIN
      RETURN 1;
    END$$
    DELIMITER ;
    SELECT 'last; value'; SELECT 2;
    """
    statements = split_sql(source)
    assert len(statements) == 5
    assert "RETURN 1;" in statements[2]
    assert statements[-2:] == ["SELECT 'last; value'", "SELECT 2"]


@pytest.mark.parametrize("source", ["SELECT 1", "SELECT 'broken;", "/* unfinished"])
def test_sql_parser_rejects_incomplete_files(source):
    with pytest.raises(ValueError, match="Unterminated"):
        split_sql(source)


def test_initial_migration_uses_selected_database():
    statements = split_sql((MIGRATIONS_DIR / "0001_initial.sql").read_text())
    assert len(statements) == 55
    assert not any(s.startswith(("CREATE DATABASE", "USE ")) for s in statements)
    assert all("ENGINE=" not in s for s in statements)


def test_startup_runs_migrations_before_serving(monkeypatch):
    import main
    calls = []
    monkeypatch.setattr(main, "get_engine", lambda: "test-engine")
    monkeypatch.setattr(main, "run_migrations", lambda engine: calls.append(engine))
    with TestClient(main.create_app()) as client:
        assert calls == ["test-engine"]
        assert client.get("/").status_code == 200


def test_failed_migration_stops_startup(monkeypatch):
    import main
    monkeypatch.setattr(main, "get_engine", lambda: "test-engine")
    def fail(engine):
        raise RuntimeError("migration failed")
    monkeypatch.setattr(main, "run_migrations", fail)
    with pytest.raises(RuntimeError, match="migration failed"):
        with TestClient(main.create_app()):
            pytest.fail("Startup must not succeed")



def test_mysql_initialization_and_restart_preserve_data(mysql_engine):
    run_migrations(mysql_engine)
    with mysql_engine.begin() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM roles")).scalar() == 6
        connection.execute(text("INSERT INTO breeds (name) VALUES ('Test breed')"))
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM breeds")).scalar() == 1
        row = connection.execute(text("SELECT completed_steps, applied_at FROM schema_migrations WHERE version = '0001_initial'")).one()
        assert row.completed_steps == 55
        assert row.applied_at is not None
    from src.core.models import Base
    assert set(Base.metadata.tables).issubset(inspect(mysql_engine).get_table_names())
    assert 'schema_migrations' in inspect(mysql_engine).get_table_names()
    assert "middle_name" in {column["name"] for column in inspect(mysql_engine).get_columns("users")}


def test_mysql_adds_middle_name_to_existing_users(mysql_engine, tmp_path):
    initial = MIGRATIONS_DIR / "0001_initial.sql"
    (tmp_path / initial.name).write_text(initial.read_text())
    run_migrations(mysql_engine, tmp_path)
    with mysql_engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO users (id, name, paternal_lastname, maternal_lastname, email, role_id, password_hash)
            VALUES ('existing-user', 'Juan Carlos', 'Lopez', 'Perez', 'existing@example.com',
                    '00000000-0000-4000-8000-000000000001', 'unused-test-hash')
        """)
    migration = MIGRATIONS_DIR / "0002_user_middle_name.sql"
    (tmp_path / migration.name).write_text(migration.read_text())
    run_migrations(mysql_engine, tmp_path)
    run_migrations(mysql_engine, tmp_path)
    with mysql_engine.begin() as connection:
        row = connection.exec_driver_sql("SELECT name, middle_name FROM users").one()
        assert row == ("Juan Carlos", None)
        connection.exec_driver_sql("UPDATE users SET name = 'Juan', middle_name = 'Carlos'")
        assert connection.exec_driver_sql("SELECT name, middle_name FROM users").one() == ("Juan", "Carlos")


def test_mysql_existing_unversioned_data_is_preserved(mysql_engine):
    with mysql_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE usuarios (id INT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO usuarios VALUES (1)")
    with pytest.raises(RuntimeError, match="unversioned"):
        run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id FROM usuarios").scalar() == 1
    assert inspect(mysql_engine).get_table_names() == ["usuarios"]


def test_mysql_resumes_after_failure_and_detects_modified_migration(mysql_engine, tmp_path):
    path = tmp_path / "0001_test.sql"
    path.write_text("CREATE TABLE IF NOT EXISTS first_table (id INT);\n"
                    "INSERT INTO missing_table VALUES (1);\n")
    with pytest.raises(RuntimeError, match="statement 2"):
        run_migrations(mysql_engine, tmp_path)
    with mysql_engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT completed_steps FROM schema_migrations").scalar() == 1
        assert connection.exec_driver_sql("SELECT applied_at FROM schema_migrations").scalar() is None
        connection.exec_driver_sql("CREATE TABLE missing_table (id INT)")
    run_migrations(mysql_engine, tmp_path)
    run_migrations(mysql_engine, tmp_path)
    with mysql_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM missing_table").scalar() == 1
    path.write_text(path.read_text() + "SELECT 1;\n")
    with pytest.raises(RuntimeError, match="modified"):
        run_migrations(mysql_engine, tmp_path)


def test_mysql_animal_permissions_and_repository(mysql_engine):
    from sqlalchemy.orm import Session
    from src.core.models import UserModel
    from src.features.animals.domain.dto import AnimalInput
    from src.features.animals.infrastructure.repository import SQLAnimalRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        grants = connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'animals:%'")).scalar()
        assert grants == 4
    with Session(mysql_engine) as session, session.begin():
        user = UserModel(name='Test', paternal_lastname='Owner', maternal_lastname='Example',
                         email='test@example.com', password_hash='unused',
                         role_id='00000000-0000-4000-8000-000000000001')
        session.add(user)
        session.flush()
        repo = SQLAnimalRepository(session)
        breed = repo.create_breed('Pelibuey', user.id)
        mother = repo.save(AnimalInput(name='Mother', sex='female', birth_date='2020-01-01'), user.id)
        child = repo.save(AnimalInput(name='Luna', siniiga='MX123', sex='female', mother_id=mother.id,
                                     breeds=[{'breed_id': breed.id, 'percentage': '100'}]), user.id)
        assert child.purity == 'pure' and child.mother.name == 'Mother'
        repo.update_breed(breed.id, 'Pelibuey updated', user.id)
        session.expire_all()
        assert repo.get(child.id).breeds[0].name == 'Pelibuey updated'
        assert repo.list('mx123', None, 0, 25).total == 1
        updated = repo.save(AnimalInput(name='Luna updated', sex='female', breeds=[]), user.id, child.id)
        assert updated.breeds == [] and updated.mother is None
        repo.delete_breed(breed.id, user.id)
        assert repo.breeds() == []


def test_mysql_organization_transfers_use_inclusive_periods(mysql_engine):
    from datetime import date
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel
    from src.features.organization.domain.dto import LocationInput, NamedInput, AssignmentInput
    from src.features.organization.infrastructure.repository import SQLOrganizationRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with Session(mysql_engine) as session, session.begin():
        user = UserModel(name='Test', paternal_lastname='Owner', maternal_lastname='Example',
                         email='owner@example.com', password_hash='unused', role_id='00000000-0000-4000-8000-000000000001')
        animal = AnimalModel(name='Luna', sex='female', birth_date=date(2020, 1, 1))
        session.add_all([user, animal])
        session.flush()
        repo = SQLOrganizationRepository(session)
        kind = next(kind for kind in repo.types() if kind.name == 'corral')
        location = repo.save_location(LocationInput(name='Corral norte', location_type_id=kind.id), user.id)
        assert location.location_type_name == 'corral'
        first = repo.save_group(NamedInput(name='Crías'), user.id)
        second = repo.save_group(NamedInput(name='Reproductoras'), user.id)
        repo.assign(first.id, AssignmentInput(animal_ids=[animal.id], effective_date='2024-01-01'), user.id)
        repo.assign(second.id, AssignmentInput(animal_ids=[animal.id], effective_date='2024-02-01', move_existing=True), user.id)
        old = repo.memberships(first.id, False, 0, 25)
        assert old.items[0].end_date == date(2024, 1, 31)
        assert repo.memberships(first.id, True, 0, 25).total == 0
        assert repo.group_response(repo.group(second.id)).member_count == 1
        removed = repo.remove(second.id, animal.id, date(2024, 3, 1), user.id)
        assert removed.end_date == date(2024, 2, 29)
        assert repo.memberships(second.id, False, 0, 25).total == 1
        assert repo.save_group(NamedInput(name='Reproductoras', active=False), user.id, second.id).active is False


def test_mysql_weight_events_and_permissions(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel, EventModel, EventWeightModel
    from src.features.weights.domain.dto import WeightInput
    from src.features.weights.infrastructure.repository import SQLWeightRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'weights:%'")).scalar() == 4
    with Session(mysql_engine) as db, db.begin():
        user = UserModel(name='Test', paternal_lastname='Owner', maternal_lastname='Example', email='weights@example.com', password_hash='unused', role_id='00000000-0000-4000-8000-000000000001')
        animal = AnimalModel(name='Luna', sex='female', birth_date=date(2023,1,1))
        db.add_all([user, animal]); db.flush()
        actor = SimpleNamespace(id=user.id, role=SimpleNamespace(id=user.role_id))
        repo = SQLWeightRepository(db)
        saved = repo.create(WeightInput(animal_id=animal.id, date='2024-01-01', weight_kg='30.50'), actor)
        assert saved['weight_kg'] == 30.50
        assert repo.page('luna', 0, 25)['total'] == 1
        assert len(repo.history(animal.id)['items']) == 1
        assert db.get(EventModel, saved['id']).role_id == user.role_id
        assert db.get(EventWeightModel, saved['id']).event_type_id == 4


def test_mysql_health_cases_and_event_subtypes(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel
    from src.features.health.domain.dto import CaseInput, ObservationInput, CaseStatusInput
    from src.features.health.infrastructure.repository import SQLHealthRepository
    run_migrations(mysql_engine);run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        from src.features.roles.domain.entities.Role import HEALTH_ACTIONS
        grants=set(connection.execute(text("SELECT r.name,p.permission FROM role_permissions p JOIN roles r ON r.id=p.role_id WHERE p.permission LIKE 'health:%'")))
        assert grants=={(name,p) for name in ('owner','administrator') for p in HEALTH_ACTIONS | {'health:read'}}
    with Session(mysql_engine) as db,db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='health@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        animal=AnimalModel(name='Luna',sex='female',birth_date=date(2023,1,1))
        db.add_all([user,animal]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id));repo=SQLHealthRepository(db)
        repo.create_observation(ObservationInput(animal_id=animal.id,date='2024-01-01',observation='Cojera'),actor)
        case=repo.create_case(CaseInput(animal_id=animal.id,start_date='2024-01-01',reason='Cojera'),actor)
        repo.change_status(case['id'],CaseStatusInput(expected_status='open',status='under_treatment'),actor)
        repo.change_status(case['id'],CaseStatusInput(expected_status='under_treatment',status='closed',closed_date='2024-01-03'),actor)
        assert repo.cases('luna','closed',0,25)['total']==1
        assert repo.observations('luna',0,25)['total']==1
        assert [a['status'] for a in repo.detail(case['id'])['activity']]==['open','under_treatment','closed']
        assert len(repo.history(animal.id)['cases'])==1


def test_mysql_health_upgrade_keeps_existing_checksum(mysql_engine, tmp_path):
    from shutil import copy2
    from hashlib import sha256
    from pathlib import Path
    migrations = Path(__file__).resolve().parents[1] / 'database' / 'migrations'
    for path in migrations.glob('*.sql'):
        if path.stem <= '0006_health':
            copy2(path, tmp_path / path.name)
    run_migrations(mysql_engine, tmp_path)
    with mysql_engine.connect() as connection:
        before = connection.execute(text("SELECT checksum FROM schema_migrations WHERE version = '0006_health'")).scalar()
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        after = connection.execute(text("SELECT checksum FROM schema_migrations WHERE version = '0006_health'")).scalar()
        precision = connection.execute(text("SELECT DATETIME_PRECISION FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'audit_logs' AND COLUMN_NAME = 'date'")).scalar()
    assert before == after == sha256((migrations / '0006_health.sql').read_bytes()).hexdigest()
    assert precision == 6


def test_mysql_diagnosis_case_trigger_and_repository(mysql_engine):
    from datetime import datetime
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import DBAPIError
    from src.core.models import UserModel, AnimalModel, EventModel, EventDiagnosisModel
    from src.features.health.domain.dto import CaseInput, DiagnosisInput
    from src.features.health.infrastructure.repository import SQLHealthRepository
    run_migrations(mysql_engine)
    with Session(mysql_engine) as db,db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='diagnosis@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        first=AnimalModel(name='Luna',sex='female')
        second=AnimalModel(name='Sol',sex='female')
        db.add_all([user,first,second]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id));repo=SQLHealthRepository(db)
        case=repo.create_case(CaseInput(animal_id=first.id,start_date='2024-01-01',reason='Cojera'),actor)
        diagnosis=repo.create_diagnosis(case['id'],DiagnosisInput(date='2024-01-03',diagnosis='Inflamación',severity='moderate'),actor)
        assert repo.detail(case['id'])['diagnoses'][0]['id']==diagnosis['id']
        assert repo.history(first.id)['diagnoses'][0]['severity']=='moderate'
        assert repo.history(second.id)['diagnoses']==[]
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                event=EventModel(animal_id=second.id,event_type_id=2,date=datetime(2024,1,3),user_id=user.id,role_id=user.role_id)
                db.add(event);db.flush()
                db.add(EventDiagnosisModel(event_id=event.id,event_type_id=2,health_case_id=case['id'],diagnosis='Wrong animal',severity='mild'))
                db.flush()


def test_mysql_treatment_generated_date_and_case_trigger(mysql_engine):
    from datetime import date,datetime
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import DBAPIError
    from src.core.models import UserModel,AnimalModel,EventModel,EventTreatmentModel
    from src.features.health.domain.dto import CaseInput,ProductInput,TreatmentInput
    from src.features.health.infrastructure.repository import SQLHealthRepository
    run_migrations(mysql_engine);run_migrations(mysql_engine)
    with Session(mysql_engine) as db,db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='treatment@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        first=AnimalModel(name='Luna',sex='female');second=AnimalModel(name='Sol',sex='female');db.add_all([user,first,second]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id));repo=SQLHealthRepository(db);catalog=repo.catalogs()
        unit=next(u['id'] for u in catalog['units'] if u['code']=='ml');kind=next(p['id'] for p in catalog['product_types'] if p['name']=='medicine');route=next(r['id'] for r in catalog['routes'] if r['name']=='oral')
        p=repo.save_product(ProductInput(name='Test product',product_type_id=kind,unit_id=unit,withdrawal_days=7),actor)
        case=repo.create_case(CaseInput(animal_id=first.id,start_date='2024-01-01',reason='Test case'),actor)
        t=repo.create_treatment(case['id'],TreatmentInput(product_id=p['id'],start_date='2024-02-28',dose_value='2.125',dose_unit_id=unit,route_id=route,duration_days=3),actor)
        assert t['end_date']==date(2024,3,2) and t['last_day']==date(2024,3,1)
        assert repo.detail(case['id'])['case']['status']=='under_treatment'
        assert repo.history(first.id)['treatments'][0]['product']['name']=='Test product'
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                event=EventModel(animal_id=second.id,event_type_id=3,date=datetime(2024,1,1),user_id=user.id,role_id=user.role_id);db.add(event);db.flush()
                db.add(EventTreatmentModel(event_id=event.id,event_type_id=3,product_id=p['id'],health_case_id=case['id'],dose_value=1,dose_unit_id=unit,route_id=route,duration_days=1,start_date=date(2024,1,1)));db.flush()


def test_mysql_program_applications_link_and_schedule(mysql_engine):
    from datetime import date,timedelta
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.core.models import UserModel,AnimalModel,EventTreatmentModel
    from src.features.health.domain.dto import ProductInput,ProgramInput,ProgramApplicationInput
    from src.features.health.infrastructure.program_repository import SQLProgramRepository
    run_migrations(mysql_engine)
    with Session(mysql_engine) as db,db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='program@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        animal=AnimalModel(name='Luna',sex='female',birth_date=date.today()-timedelta(days=365));db.add_all([user,animal]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id));repo=SQLProgramRepository(db);catalog=repo.catalogs()
        unit=next(u['id'] for u in catalog['units'] if u['code']=='ml');kind=next(p['id'] for p in catalog['product_types'] if p['name']=='vaccine');route=next(r['id'] for r in catalog['routes'] if r['name']=='subcutaneous')
        product=repo.save_product(ProductInput(name='Program product',product_type_id=kind,unit_id=unit),actor)
        program=repo.save_program(ProgramInput(name='Vaccination program',product_id=product['id'],interval_days=90,minimum_age_days=30,notice_days=7),actor)
        assert repo.schedule(program['id'],'','attention',0,25)['items'][0]['status']=='overdue'
        treatment=repo.apply_program(program['id'],ProgramApplicationInput(animal_id=animal.id,start_date=date.today(),dose_value=1,dose_unit_id=unit,route_id=route,duration_days=1),actor)
        assert db.get(EventTreatmentModel,(treatment['id'],product['id'])).program_id==program['id']
        schedule=repo.schedule(program['id'],'','all',0,25)
        assert schedule['items'][0]['due_date']==date.today()+timedelta(days=90)
        assert repo.schedule(program['id'],'','attention',0,25)['total']==0
        assert repo.history(animal.id)['treatments'][0]['program_name']=='Vaccination program'


def test_mysql_reproduction_birth_parentage_and_restart(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel, ExitModel
    from src.features.breeding.domain.dto import MatingInput, PregnancyInput, BirthInput
    from src.features.breeding.infrastructure.repository import SQLBreedingRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'breeding:%'")).scalar() == 4
        assert connection.execute(text("SELECT COUNT(*) FROM birth_types")).scalar() == 4
    with Session(mysql_engine) as db, db.begin():
        user = UserModel(name='Test', paternal_lastname='Owner', maternal_lastname='Example', email='breeding@example.com', password_hash='unused', role_id='00000000-0000-4000-8000-000000000001')
        mother = AnimalModel(name='Luna', sex='female', birth_date=date(2020,1,1))
        father = AnimalModel(name='Trueno', sex='male', birth_date=date(2020,1,1))
        db.add_all([user,mother,father]); db.flush()
        actor = SimpleNamespace(id=user.id, role=SimpleNamespace(id=user.role_id))
        repo = SQLBreedingRepository(db)
        mating = repo.create('mating', MatingInput(animal_id=mother.id, male_id=father.id, date='2024-01-01'), actor)
        repo.create('pregnancy', PregnancyInput(animal_id=mother.id, date='2024-02-01', result='pregnant', mating_event_id=mating['id']), actor)
        birth = repo.create('birth', BirthInput(animal_id=mother.id, father_id=father.id, date='2024-06-01', birth_type_id=1, offspring=[{'name':'Estrella','sex':'female','birth_weight_kg':'3.25'}, {'name':'Sol','sex':'male','alive':False}]), actor)
        assert len(birth['offspring']) == 2
        child = db.get(AnimalModel,birth['offspring'][0]['animal']['id'])
        assert (child.mother_id,child.father_id,child.birth_date)==(mother.id,father.id,date(2024,6,1))
        assert repo.history(child.id)['items'][0]['id']==birth['id']
        assert len(repo.history(mother.id)['items'])==3
        assert db.query(ExitModel).count()==1


def test_mysql_exit_state_and_group_closure(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel, AnimalGroupModel, GroupAnimalModel
    from src.features.exits.domain.dto import ExitInput
    from src.features.exits.infrastructure.repository import SQLExitRepository
    from src.features.animals.infrastructure.repository import SQLAnimalRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'exits:%'")).scalar() == 4
    with Session(mysql_engine) as db, db.begin():
        user = UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='exit@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        animal = AnimalModel(name='Luna',sex='female',birth_date=date(2020,1,1))
        group = AnimalGroupModel(name='Reproductoras')
        db.add_all([user,animal,group]);db.flush()
        period = GroupAnimalModel(group_id=group.id,animal_id=animal.id,start_date=date(2024,1,1))
        db.add(period);db.flush()
        actor = SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id))
        repo = SQLExitRepository(db)
        departure = repo.create(ExitInput(animal_id=animal.id,date='2024-06-01',exit_type='transfer',reason='Transfer to another herd'),actor)
        assert repo.history(animal.id)['items'][0]['id']==departure['id']
        assert period.end_date==date(2024,6,1)
        detail = SQLAnimalRepository(db).get(animal.id)
        assert detail.status=='transfer' and detail.exit_date==date(2024,6,1)
        assert SQLAnimalRepository(db).list('',None,0,25,active=True).total==0


def test_mysql_finance_precision_sales_and_restart(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from decimal import Decimal
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel
    from src.features.finance.domain.dto import ExpenseInput, IncomeInput, SupplierInput
    from src.features.finance.infrastructure.repository import SQLFinanceRepository
    from src.features.exits.domain.dto import ExitInput
    from src.features.exits.infrastructure.repository import SQLExitRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'finance:%'")).scalar() == 4
        assert connection.execute(text("SELECT COUNT(*) FROM expense_categories")).scalar() == 5
        assert connection.execute(text("SELECT COUNT(*) FROM income_categories")).scalar() == 2
    with Session(mysql_engine) as db, db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='finance@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        animal=AnimalModel(name='Aurora',sex='female',birth_date=date(2020,1,1))
        db.add_all([user,animal]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id))
        repo=SQLFinanceRepository(db)
        supplier=repo.save_supplier(SupplierInput(name='Feed supplier'),actor)
        expense_category=next(c['id'] for c in repo.categories('expense') if c['name']=='feed')
        income_category=next(c['id'] for c in repo.categories('income') if c['name']=='animal_sales')
        repo.save_money('expense',ExpenseInput(category_id=expense_category,supplier_id=supplier['id'],amount='100.10',date='2024-06-01'),actor)
        sale=SQLExitRepository(db).create(ExitInput(animal_id=animal.id,exit_type='sale',date='2024-06-01',reason='Sale'),actor)
        received=repo.save_money('income',IncomeInput(category_id=income_category,amount='300.30',date='2024-06-01',exit_event_id=sale['id']),actor)
        assert received['sale']['animal_name']=='Aurora'
        assert repo.summary(None,None)['balance']==Decimal('200.20')
        assert repo.sale_options('')==[]


def test_mysql_feeding_prices_and_decimal_cost(mysql_engine):
    from datetime import date
    from types import SimpleNamespace
    from decimal import Decimal
    from sqlalchemy.orm import Session
    from src.core.models import UserModel, AnimalModel
    from src.features.feeding.domain.dto import FeedInput, PriceInput, FeedingInput
    from src.features.feeding.infrastructure.repository import SQLFeedingRepository
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM role_permissions WHERE permission LIKE 'feeding:%'")).scalar()==4
    with Session(mysql_engine) as db,db.begin():
        user=UserModel(name='Test',paternal_lastname='Owner',maternal_lastname='Example',email='feeding@example.com',password_hash='unused',role_id='00000000-0000-4000-8000-000000000001')
        animal=AnimalModel(name='Luna',sex='female',birth_date=date(2020,1,1))
        db.add_all([user,animal]);db.flush()
        actor=SimpleNamespace(id=user.id,role=SimpleNamespace(id=user.role_id));repo=SQLFeedingRepository(db)
        unit=next(u['id'] for u in repo.units() if u['code']=='kg')
        feed=repo.save_feed(FeedInput(name='Sheep feed',unit_id=unit),actor)
        repo.add_price(feed['id'],PriceInput(effective_from='2024-01-01',unit_cost='10.1250'),actor)
        repo.add_price(feed['id'],PriceInput(effective_from='2024-02-01',unit_cost='12.5000'),actor)
        first=repo.create(FeedingInput(feed_id=feed['id'],animal_id=animal.id,date='2024-01-31',quantity='1.25'),actor)
        second=repo.create(FeedingInput(feed_id=feed['id'],animal_id=animal.id,date='2024-02-01',quantity='2'),actor)
        assert first['cost']==Decimal('12.66') and second['cost']==Decimal('25.00')
        page=repo.page('',animal.id,None,None,None,0,1)
        assert len(page['items'])==1 and page['total']==2 and page['total_cost']==Decimal('37.66')


def test_mysql_profile_photo_upgrade_preserves_users_and_restarts(mysql_engine, tmp_path):
    from shutil import copy2
    from src.core.migrations import MIGRATIONS_DIR
    for path in MIGRATIONS_DIR.glob('*.sql'):
        if path.name < '0032':
            copy2(path, tmp_path / path.name)
    run_migrations(mysql_engine, tmp_path)
    with mysql_engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO users (id, name, paternal_lastname, maternal_lastname, email, role_id, password_hash)
            VALUES ('photo-existing-user', 'Profile', 'Example', 'Test', 'profile@example.com',
                    '00000000-0000-4000-8000-000000000001', 'unchanged-hash')
        """)
    run_migrations(mysql_engine)
    run_migrations(mysql_engine)
    with mysql_engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT name, password_hash, profile_photo_url FROM users WHERE id='photo-existing-user'").one()
        assert tuple(row) == ('Profile', 'unchanged-hash', None)
        assert connection.exec_driver_sql(
            "SELECT applied_at FROM schema_migrations WHERE version='0032_profile_photo'").scalar() is not None
