from datetime import datetime
from uuid import uuid4
from sqlalchemy import func, select
from src.core.models import AuditModel, EventModel, UserModel
from src.features.audit.domain.changes import changed_fields
from tests.conftest import login
from tests.test_animals import animal


def seed(factory):
    with factory.begin() as db:
        owner = db.scalar(select(UserModel).where(UserModel.email == 'owner@example.com'))
        worker = db.scalar(select(UserModel).where(UserModel.email == 'worker@example.com'))
        a = AuditModel(table='users', record_id=worker.id, user_id=owner.id, action='UPDATE',
            date=datetime(2024,6,1,5,59,59), old_values={'name':'Antes','active':True,'middle_name':None,
                'password_hash':'private-hash', 'nested':{'accessToken':'private-token','value':1}},
            new_values={'name':'Después','active':False,'password_changed':True,
                'nested':{'password':'private-password','value':2},'items':[{'api_key':'private-key','name':'visible'}]})
        b = AuditModel(table='roles', record_id=str(uuid4()), user_id=owner.id, action='DELETE',
            date=datetime(2024,6,1,6), old_values={'name':'Rol eliminado','permissions':['health:read']})
        c = AuditModel(table='feeds',record_id=str(uuid4()),user_id=None,action='INSERT',
            date=datetime(2024,6,2,6),new_values={'name':'Alimento registrado'})
        db.add_all([a,b,c]);db.flush()
        return a.id,b.id,c.id,owner.id,worker.id


def test_audit_filters_order_pagination_and_local_boundaries(api):
    client,factory=api
    ids=seed(factory);h=login(client)
    page=client.get('/api/v1/audit?limit=2',headers=h).json()
    assert page['total']==3 and [r['id'] for r in page['items']]==[ids[2],ids[1]]
    assert 'old_values' not in page['items'][0] and 'changes' not in page['items'][0]
    assert page['items'][0]['actor'] is None and page['items'][0]['module']=='feeding'
    assert page['items'][1]['date'].endswith('Z')
    assert client.get('/api/v1/audit?offset=2&limit=2',headers=h).json()['items'][0]['id']==ids[0]
    filters={'date_from':'2024-06-01T00:00:00-06:00','date_before':'2024-06-02T00:00:00-06:00'}
    result=client.get('/api/v1/audit',params=filters,headers=h).json()
    assert [r['id'] for r in result['items']]==[ids[1]]
    for query,expected in [('module=roles',ids[1]),('action=UPDATE',ids[0]),('user_id=system',ids[2]),
                           ('q=eliminado',ids[1]),('record_id='+ids[4],ids[0])]:
        data=client.get('/api/v1/audit?'+query,headers=h).json()
        assert [r['id'] for r in data['items']]==[expected]
    assert client.get('/api/v1/audit?user_id='+ids[3],headers=h).json()['total']==2
    assert client.get('/api/v1/audit?q=%25',headers=h).json()['total']==0
    users=client.get('/api/v1/audit/users',headers=h).json()
    assert [u['id'] for u in users]==[ids[3]] # includes the logged-in actor
    assert client.get('/api/v1/audit/users?q=nobody',headers=h).json()==[]


def test_detail_redaction_and_missing_vs_null(api):
    client,factory=api
    ids=seed(factory);h=login(client)
    response=client.get('/api/v1/audit/'+ids[0],headers=h)
    assert response.status_code==200,response.text
    assert 'private-' not in response.text and 'password_hash' not in response.text
    d=response.json();changes={c['field']:c for c in d['changes']}
    assert changes['name']['before']=='Antes' and changes['name']['after']=='Después'
    assert changes['middle_name']['before_present'] and not changes['middle_name']['after_present']
    assert changes['middle_name']['before'] is None
    assert changes['password_changed']['after'] is True
    assert changes['nested.value']['after']==2
    assert d['new_values']['items']==[{'name':'visible'}]
    removed=client.get('/api/v1/audit/'+ids[1],headers=h).json()
    assert removed['record_name']=='Rol eliminado' and removed['new_values'] is None
    assert all(not c['after_present'] for c in removed['changes'])
    assert client.get('/api/v1/audit/'+str(uuid4()),headers=h).status_code==404
    assert changed_fields(None,None)==[]
    assert changed_fields({'same':True},{'same':True})==[]


def test_real_writes_and_event_module_classification(api):
    client,factory=api;h=login(client)
    saved=animal(client,h,name='Luna')
    with factory.begin() as db:
        owner=db.scalar(select(UserModel).where(UserModel.email=='owner@example.com'))
        e=EventModel(animal_id=saved['id'],event_type_id=3,date=datetime(2024,1,1),
                     user_id=owner.id,role_id=owner.role_id)
        db.add(e);db.flush()
        db.add(AuditModel(table='events',record_id=e.id,user_id=owner.id,action='INSERT',
                         new_values={'event_type_id':3,'animal_id':saved['id']}))
        db.add(AuditModel(table='events',record_id=str(uuid4()),user_id=owner.id,action='DELETE',
                         old_values={'event_type_id':8}))
    animals=client.get('/api/v1/audit?module=animals',headers=h).json()
    assert animals['total']==1 and animals['items'][0]['record_name']=='Luna'
    health=client.get('/api/v1/audit?module=health',headers=h).json()
    assert health['total']==1 and health['items'][0]['record_name']=='Luna'
    assert health['items'][0]['event_type_id']==3
    assert client.get('/api/v1/audit?module=exits',headers=h).json()['total']==1


def test_audit_requires_dedicated_permission_and_is_read_only(api):
    client,factory=api;ids=seed(factory)
    worker=login(client,'worker@example.com')
    for path in ['/audit','/audit/users','/audit/'+ids[0]]:
        assert client.get('/api/v1'+path).status_code==401
        assert client.get('/api/v1'+path,headers=worker).status_code==403
    h=login(client)
    for query in ['module=invalid','action=PATCH','limit=101','offset=-1','user_id=invalid',
                  'date_from=2024-01-01T00:00:00',
                  'date_from=2024-02-01T00:00:00Z&date_before=2024-01-01T00:00:00Z']:
        assert client.get('/api/v1/audit?'+query,headers=h).status_code==422
    with factory() as db:
        before=db.scalar(select(func.count()).select_from(AuditModel))
    for method in ['post','put','delete']:
        assert getattr(client,method)('/api/v1/audit/'+ids[0],headers=h).status_code==405
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditModel))==before


def test_audit_only_role_can_read_and_resolves_role_changes(api):
    from src.core.models import RolePermissionModel, RoleModel
    client,factory=api
    with factory.begin() as db:
        worker=db.scalar(select(UserModel).where(UserModel.email=='worker@example.com'))
        owner=db.scalar(select(UserModel).where(UserModel.email=='owner@example.com'))
        manager=db.scalar(select(RoleModel).where(RoleModel.name=='manager'))
        db.add(RolePermissionModel(role_id=worker.role_id,permission='audit:read'))
        audit=AuditModel(table='users',record_id=owner.id,user_id=owner.id,action='UPDATE',
                        old_values={'role_id':worker.role_id},new_values={'role_id':manager.id})
        db.add(audit);db.flush();audit_id=audit.id
    h=login(client,'worker@example.com')
    assert client.get('/api/v1/users',headers=h).status_code==403
    d=client.get('/api/v1/audit/'+audit_id,headers=h).json()
    assert d['changes'][0]['before_label']=='worker' and d['changes'][0]['after_label']=='manager'
    assert client.get('/api/v1/audit/users',headers=h).status_code==200


def test_group_catalog_uses_group_module(api):
    client,factory=api;h=login(client)
    with factory.begin() as db:
        audit=AuditModel(table='animal_groups',record_id=str(uuid4()),action='INSERT',
                        new_values={'name':'Lote de hembras'})
        db.add(audit)
    page=client.get('/api/v1/audit?module=groups',headers=h).json()
    assert page['total']==1 and page['items'][0]['record_name']=='Lote de hembras'


def test_record_history_does_not_mix_catalogs_with_same_numeric_id(api):
    client,factory=api;h=login(client)
    with factory.begin() as db:
        db.add_all([AuditModel(table=table,record_id='1',action='INSERT',new_values={'name':table})
                    for table in ['breeds','income_categories','expense_categories']])
    page=client.get('/api/v1/audit?table=breeds&record_id=1',headers=h).json()
    assert page['total']==1 and page['items'][0]['table']=='breeds'
