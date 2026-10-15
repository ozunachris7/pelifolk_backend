from sqlalchemy import func, select
from src.core.models import AuditModel, RoleModel, RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal


def test_genealogy_branches_shared_ancestor_children_and_historical_exits(api):
    client,factory=api;h=login(client)
    grandma=animal(client,h,name='Abuela común',birth_date='2015-01-01')
    grandpa=animal(client,h,name='Abuelo materno',sex='male',birth_date='2015-01-01')
    mother=animal(client,h,name='Madre',birth_date='2018-01-01',mother_id=grandma['id'],father_id=grandpa['id'])
    father=animal(client,h,name='Padre',sex='male',birth_date='2018-01-01',mother_id=grandma['id'])
    root=animal(client,h,name='Luna',birth_date='2020-01-01',mother_id=mother['id'],father_id=father['id'])
    son=animal(client,h,name='Hijo',sex='male',birth_date='2022-01-01',mother_id=root['id'])
    daughter=animal(client,h,name='Hija',birth_date='2023-01-01',mother_id=root['id'])
    animal(client,h,name='Otro animal',birth_date='2023-01-01')
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':grandma['id'],'exit_type':'sale','date':'2024-01-01','reason':'Venta'}).status_code==201
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    r=client.get('/api/v1/animals/'+root['id']+'/genealogy',headers=h,params={'limit':1});assert r.status_code==200,r.text
    page=r.json();tree=page['tree']
    assert tree['animal']['id']==root['id']
    assert tree['mother']['animal']['id']==mother['id'] and tree['father']['animal']['id']==father['id']
    assert tree['mother']['mother']['animal']['id']==tree['father']['mother']['animal']['id']==grandma['id']
    assert tree['mother']['mother']['animal']['status']=='sale'
    assert tree['mother']['father']['animal']['id']==grandpa['id'] and tree['father']['father'] is None
    assert tree['mother']['mother']['mother'] is None
    assert page['total_children']==2 and page['female_children']==1 and page['male_children']==1
    assert [c['id'] for c in page['children']]==[daughter['id']]
    second=client.get('/api/v1/animals/'+root['id']+'/genealogy',headers=h,params={'limit':1,'offset':1}).json()
    assert [c['id'] for c in second['children']]==[son['id']] and second['total_children']==2
    paternal=client.get('/api/v1/animals/'+father['id']+'/genealogy',headers=h).json()
    assert [c['id'] for c in paternal['children']]==[root['id']]
    leaf=client.get('/api/v1/animals/'+son['id']+'/genealogy',headers=h).json()
    assert leaf['tree']['father'] is None and leaf['children']==[] and leaf['total_children']==0
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before


def test_genealogy_permissions_unknown_and_validation(api):
    client,factory=api;h=login(client);a=animal(client,h,siniiga='MX123')
    path='/api/v1/animals/'+a['id']+'/genealogy'
    assert client.get(path).status_code==401
    worker=login(client,'worker@example.com');assert client.get(path,headers=worker).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    page=client.get(path,headers=worker).json()
    assert page['tree']['mother'] is None and page['tree']['father'] is None
    assert page['children']==[]
    for params in ({'offset':-1},{'limit':0},{'limit':101}):assert client.get(path,headers=h,params=params).status_code==422
    assert client.get('/api/v1/animals/not-a-uuid/genealogy',headers=h).status_code==422
    assert client.get('/api/v1/animals/00000000-0000-4000-8000-000000000099/genealogy',headers=h).status_code==404
