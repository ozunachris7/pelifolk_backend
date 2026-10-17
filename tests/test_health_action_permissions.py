from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select, delete, func
from src.core.models import RoleModel, RolePermissionModel, AuditModel
from src.core.migrations import split_sql
from src.features.roles.domain.entities.Role import HEALTH_ACTIONS
from tests.conftest import login
from tests.test_animals import animal
from tests.test_doses import setup, dose


def grant(factory, permissions):
    with factory.begin() as db:
        role = db.scalar(select(RoleModel).where(RoleModel.name == 'worker'))
        db.execute(delete(RolePermissionModel).where(RolePermissionModel.role_id == role.id))
        db.add_all(RolePermissionModel(role_id=role.id,permission=p) for p in permissions)


ID = '00000000-0000-4000-8000-000000000001'
ROUTES = [
    ('POST','observations','observations:create'),
    ('POST','cases','cases:write'),
    ('PATCH',f'cases/{ID}/status','cases:write'),
    ('POST',f'observations/{ID}/case-link','cases:write'),
    ('POST',f'cases/{ID}/diagnoses','diagnoses:create'),
    ('POST',f'cases/{ID}/treatments','treatments:create'),
    ('POST',f'treatments/{ID}/products/{ID}/doses','doses:create'),
    ('POST',f'cases/{ID}/followups','followups:create'),
    ('POST','products','products:write'),
    ('PUT',f'products/{ID}','products:write'),
    ('POST','ingredients','products:write'),
    ('PUT','ingredients/1','products:write'),
    ('DELETE','ingredients/1','products:write'),
    ('POST','programs','programs:write'),
    ('PUT',f'programs/{ID}','programs:write'),
    ('POST',f'programs/{ID}/applications','program_applications:create'),
    ('POST','reactions','reactions:write'),
    ('POST',f'reactions/{ID}/closure','reactions:write'),
    ('POST','incidents','incidents:write'),
    ('POST',f'incidents/{ID}/followups','incidents:write'),
]


def test_every_write_route_requires_its_action_not_an_unrelated_action(api):
    client,factory=api;h=login(client,'worker@example.com')
    for method,path,action in ROUTES:
        grant(factory,{'health:read'} | (HEALTH_ACTIONS - {'health:'+action}))
        r=client.request(method,'/api/v1/health/'+path,headers=h,json={})
        assert r.status_code==403,(path,r.status_code,r.text)
        grant(factory,{'health:read','health:'+action})
        # Valid authorization reaches payload/domain validation; no records are created.
        r=client.request(method,'/api/v1/health/'+path,headers=h,json={})
        assert r.status_code in (404,422),(path,r.status_code,r.text)


def test_observer_can_report_but_cannot_diagnose_and_revocation_is_immediate(api):
    client,factory=api;owner=login(client);worker=login(client,'worker@example.com')
    a=animal(client,owner,birth_date='2020-01-01')
    grant(factory,{'health:read','health:observations:create'})
    data={'animal_id':a['id'],'date':'2024-01-01','observation':'Observación para prueba de permisos.'}
    assert client.post('/api/v1/health/observations',headers=worker,json=data).status_code==201
    assert client.get('/api/v1/health/cases',headers=worker).status_code==200
    assert client.post('/api/v1/health/cases',headers=worker,json={'animal_id':a['id'],'start_date':'2024-01-01','reason':'Caso'}).status_code==403
    grant(factory,{'health:read'})
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    assert client.post('/api/v1/health/observations',headers=worker,json=data).status_code==403
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before
    grant(factory,{'health:observations:create'})
    assert client.post('/api/v1/health/observations',headers=worker,json=data).status_code==403


def test_dose_recorder_cannot_indicate_treatment(api):
    client,factory=api;owner=login(client);worker=login(client,'worker@example.com');a,c,p,t=setup(client,owner)
    grant(factory,{'health:read','health:doses:create'})
    assert dose(client,worker,t,p).status_code==201
    assert client.post('/api/v1/health/cases/'+c['id']+'/treatments',headers=worker,json={'product_id':p['id'],'start_date':'2024-01-03','dose_value':'2','dose_unit_id':1,'route_id':1,'duration_days':1}).status_code==403


def test_role_catalog_and_read_dependency(api):
    client,factory=api;h=login(client)
    catalog=client.get('/api/v1/roles/permissions',headers=h)
    assert catalog.status_code==200,catalog.text
    assert HEALTH_ACTIONS.issubset(catalog.json()) and 'health:write' not in catalog.json()
    assert client.post('/api/v1/roles',headers=h,json={'name':'observer','permissions':['health:observations:create']}).status_code==422
    assert client.post('/api/v1/roles',headers=h,json={'name':'observer','permissions':['health:read','health:observations:create']}).status_code==201
    assert client.post('/api/v1/roles',headers=h,json={'name':'legacy','permissions':['health:write']}).status_code==422


def test_migration_preserves_only_existing_health_grants_and_is_resumable(api):
    client,factory=api
    statements=split_sql(Path('database/migrations/0028_health_action_permissions.sql').read_text())
    assert len(statements)==2
    with factory.begin() as db:
        worker=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add(RolePermissionModel(role_id=worker.id,permission='health:write'))
        db.add(RolePermissionModel(role_id=worker.id,permission='health:doses:create'))
        db.flush()
        # SQLite equivalent of MySQL's duplicate-key no-op; exercise the actual SELECT and deletion.
        insert=statements[0] if db.bind.dialect.name=='mysql' else statements[0].split('ON DUPLICATE KEY')[0].replace('INSERT INTO','INSERT OR IGNORE INTO',1)
        for _ in range(2):
            db.connection().exec_driver_sql(insert)
            db.connection().exec_driver_sql(statements[1])
        permissions=set(db.scalars(select(RolePermissionModel.permission).where(RolePermissionModel.role_id==worker.id)))
        assert permissions==HEALTH_ACTIONS | {'health:read'}
        tech=db.scalar(select(RoleModel).where(RoleModel.name=='livestock_technician'))
        assert not list(db.scalars(select(RolePermissionModel.permission).where(RolePermissionModel.role_id==tech.id)))
