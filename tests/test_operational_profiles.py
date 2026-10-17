"""Reference profiles configured through the API. Never applied to real ranch roles."""
import json
from pathlib import Path
import pytest
from sqlalchemy import select,func
from src.core.models import AuditModel, EventModel, TreatmentDoseModel, UserModel
from tests.conftest import login,PASSWORD
from tests.test_animals import animal
from tests.test_treatments import product
from tests.test_doses import dose
from tests.test_feeding import feed_setup
from tests.test_finance import category
from tests.test_incidents import report,follow
from tests.test_health_action_permissions import ROUTES as HEALTH_WRITES

PROFILES=json.loads((Path(__file__).parent/'fixtures/profile_matrix.json').read_text())
READS={
    '/animals':'animals:read','/breeds':'animals:read','/groups':'groups:read','/locations':'locations:read',
    '/weights':'weights:read','/breeding/events':'breeding:read','/exits':'exits:read',
    '/health/observations':'health:read','/health/cases':'health:read','/health/products':'health:read',
    '/health/programs':'health:read','/health/reactions':'health:read','/health/incidents':'health:read',
    '/finance/incomes':'finance:read','/finance/expenses':'finance:read','/finance/profitability':'finance:read',
    '/feeding/feeds':'feeding:read','/feeding/consumptions':'feeding:read',
    '/audit':'audit:read','/users':'users:read','/roles':'roles:read',
    '/reports/animals':'animals:read','/reports/weights':'weights:read',
}
WRITES={
    '/animals':'animals:write','/groups':'groups:write','/locations':'locations:write','/weights':'weights:write',
    '/breeding/matings':'breeding:write','/exits':'exits:write','/finance/incomes':'finance:write',
    '/finance/expenses':'finance:write','/feeding/feeds':'feeding:write','/feeding/consumptions':'feeding:write',
    '/users':'users:write','/roles':'roles:write',
}


@pytest.fixture
def profiles(api):
    client,factory=api;owner=login(client)
    roles={r['name']:r for r in client.get('/api/v1/roles',headers=owner).json()}
    for name,permissions in PROFILES.items():
        if name=='owner':continue
        r=client.put('/api/v1/roles/'+roles[name]['id'],headers=owner,json={'name':name,'permissions':permissions})
        assert r.status_code==200,r.text
    return client,factory,owner,roles


@pytest.mark.parametrize('name',PROFILES)
def test_six_profiles_read_write_matrix_and_logout(profiles,name):
    client,factory,owner,roles=profiles;h=login(client,name+'@example.com');permissions=PROFILES[name]
    me=client.get('/api/v1/auth/me',headers=h).json()
    assert me['role_name']==name and set(me['permissions'])==set(permissions)
    for path,permission in READS.items():
        r=client.get('/api/v1'+path,headers=h)
        assert r.status_code==(200 if permission in permissions else 403),(name,path,r.status_code,r.text)
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    for path,permission in WRITES.items():
        r=client.post('/api/v1'+path,headers=h,json={})
        assert r.status_code==(422 if permission in permissions else 403),(name,path,r.status_code,r.text)
    for method,path,permission in HEALTH_WRITES:
        allowed='health:'+permission in permissions and 'health:read' in permissions
        r=client.request(method,'/api/v1/health/'+path,headers=h,json={})
        assert r.status_code in ((404,422) if allowed else (403,)),(name,path,r.status_code,r.text)
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before
    summary=client.get('/api/v1/dashboard/summary',headers=h).json()
    for field,permission in [('herd','animals:read'),('health','health:read'),('breeding','breeding:read'),('finance','finance:read'),('feeding','feeding:read')]:
        assert (summary[field] is not None)==(permission in permissions),(name,field)
    assert client.post('/api/v1/auth/logout',headers=h).status_code==204
    assert client.get('/api/v1/auth/me',headers=h).status_code==401


def test_six_profiles_collaborate_without_crossing_clinical_or_financial_permissions(profiles):
    client,factory,owner,roles=profiles
    sessions={name:login(client,name+'@example.com') for name in PROFILES}
    manager,worker,vet,tech,admin=[sessions[n] for n in ['manager','worker','veterinarian','livestock_technician','administrator']]
    a=animal(client,manager,name='Hembra de simulación',birth_date='2020-01-01')
    male=animal(client,manager,name='Macho de simulación',sex='male',birth_date='2019-01-01')
    o=client.post('/api/v1/health/observations',headers=worker,json={'animal_id':a['id'],'date':'2024-01-01','observation':'SIMULACIÓN: hallazgo para verificar colaboración entre perfiles.'})
    assert o.status_code==201,o.text
    case=client.post('/api/v1/health/cases',headers=vet,json={'animal_id':a['id'],'start_date':'2024-01-01','reason':'SIMULACIÓN: seguimiento entre perfiles.','observation_id':o.json()['id']})
    assert case.status_code==201,case.text;case=case.json()
    diagnosis={'date':'2024-01-02','diagnosis':'SIMULACIÓN: texto diagnóstico para verificar permisos.','severity':'mild'}
    assert client.post('/api/v1/health/cases/'+case['id']+'/diagnoses',headers=worker,json=diagnosis).status_code==403
    assert client.post('/api/v1/health/cases/'+case['id']+'/diagnoses',headers=vet,json=diagnosis).status_code==201
    p=product(client,vet).json()
    regimen={'product_id':p['id'],'start_date':'2024-01-03','dose_value':'2','dose_unit_id':1,'route_id':1,'duration_days':1}
    t=client.post('/api/v1/health/cases/'+case['id']+'/treatments',headers=vet,json=regimen)
    assert t.status_code==201,t.text;t=t.json()
    applied=dose(client,worker,t,p,administered_by='SIMULACIÓN: responsable de la aplicación',notes='SIMULACIÓN: cantidad de ejemplo, sin aplicación real.')
    assert applied.status_code==201,applied.text
    assert client.post('/api/v1/health/cases/'+case['id']+'/treatments',headers=tech,json=regimen).status_code==403
    w=client.post('/api/v1/weights',headers=tech,json={'animal_id':a['id'],'date':'2024-01-04','weight_kg':'25'})
    assert w.status_code==201,w.text
    mating=client.post('/api/v1/breeding/matings',headers=tech,json={'animal_id':a['id'],'male_id':male['id'],'date':'2024-01-04'})
    assert mating.status_code==201,mating.text
    pregnancy=client.post('/api/v1/breeding/pregnancy-diagnoses',headers=tech,json={'animal_id':a['id'],'date':'2024-02-01','result':'pregnant','mating_event_id':mating.json()['id']})
    assert pregnancy.status_code==201,pregnancy.text
    birth=client.post('/api/v1/breeding/births',headers=tech,json={'animal_id':a['id'],'father_id':male['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'Cría simulada','sex':'female','birth_weight_kg':'3.2'}]})
    assert birth.status_code==201,birth.text
    feed=feed_setup(client,factory,manager)
    assert client.post('/api/v1/feeding/feeds/'+feed['id']+'/prices',headers=manager,json={'effective_from':'2024-01-01','unit_cost':'10'}).status_code==201
    consumption=client.post('/api/v1/feeding/consumptions',headers=worker,json={'animal_id':a['id'],'feed_id':feed['id'],'date':'2024-01-04','quantity':'1'})
    assert consumption.status_code==201,consumption.text
    cat=category(client,manager,'expense','Sanidad simulada');inc=category(client,admin,'income','Ingreso simulado')
    expense=client.post('/api/v1/finance/expenses',headers=manager,json={'category_id':cat['id'],'amount':'50','date':'2024-01-04'})
    assert expense.status_code==201,expense.text
    allocated=client.put('/api/v1/finance/expenses/'+expense.json()['id']+'/allocations',headers=manager,json={'allocations':[{'kind':'health_case','target_id':case['id'],'percentage':'100'}]})
    assert allocated.status_code==200,allocated.text
    income=client.post('/api/v1/finance/incomes',headers=admin,json={'category_id':inc['id'],'animal_id':a['id'],'amount':'100','date':'2024-01-05'})
    assert income.status_code==201,income.text
    result=client.get('/api/v1/finance/profitability',headers=manager,params={'animal_id':a['id']}).json()
    assert result['summary']=={'income':'100.00','expenses':'50.00','result':'50.00'}
    for h in [worker,vet,tech]:
        assert client.get('/api/v1/finance/profitability',headers=h).status_code==403
        assert client.get('/api/v1/health/treatments/'+t['id']+'/products/'+p['id']+'/cost',headers=h).status_code==403
    # Clinical history still attributes each capture to its authenticated author.
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=vet).json()
    assert detail['observations'][0]['recorded_by'].startswith('Worker')
    assert detail['diagnoses'][0]['recorded_by'].startswith('Veterinarian')
    with factory() as db:
        event=db.get(EventModel,t['id']);applied_row=db.get(TreatmentDoseModel,applied.json()['id'])
        assert event.role_id==roles['veterinarian']['id'] and applied_row.role_id==roles['worker']['id']
    # Permission removal affects the already issued token, with consultation retained.
    permissions=[p for p in PROFILES['worker'] if p!='health:doses:create']
    changed=client.put('/api/v1/roles/'+roles['worker']['id'],headers=owner,json={'name':'worker','permissions':permissions})
    assert changed.status_code==200,changed.text
    assert dose(client,worker,t,p,applied_at='2024-01-03T22:30:00-06:00').status_code==403
    assert client.get('/api/v1/health/cases/'+case['id'],headers=worker).status_code==200
    assert 'health:doses:create' not in client.get('/api/v1/auth/me',headers=worker).json()['permissions']


def test_two_responsibles_cannot_overwrite_stale_case_state_or_incident_followup(profiles):
    client,factory,owner,roles=profiles;vet=login(client,'veterinarian@example.com');manager=login(client,'manager@example.com');worker=login(client,'worker@example.com')
    a=animal(client,manager,birth_date='2020-01-01')
    case=client.post('/api/v1/health/cases',headers=vet,json={'animal_id':a['id'],'reason':'SIMULACIÓN: coordinación','start_date':'2024-01-01'}).json()
    url='/api/v1/health/cases/'+case['id']+'/status'
    assert client.patch(url,headers=vet,json={'expected_status':'open','status':'under_treatment'}).status_code==200
    assert client.patch(url,headers=manager,json={'expected_status':'open','status':'closed','closed_date':'2024-01-05'}).status_code==409
    assert client.get('/api/v1/health/cases/'+case['id'],headers=manager).json()['case']['status']=='under_treatment'
    incident=report(client,worker,a).json()
    assert follow(client,worker,incident).status_code==201
    assert follow(client,manager,incident,status='closed',notes='Otra persona intenta guardar con una versión anterior.').status_code==409
    latest=client.get('/api/v1/health/incidents/'+incident['id'],headers=manager).json()
    assert latest['incident']['version']==1 and latest['followups']['total']==1


def test_administrator_cannot_grant_owner_only_rectification_or_change_owner(profiles):
    client,factory,owner,roles=profiles;admin=login(client,'administrator@example.com')
    owner_me=client.get('/api/v1/auth/me',headers=owner).json()
    assert client.patch('/api/v1/users/'+owner_me['id'],headers=admin,json={'password':'Never-apply-this-123'}).status_code==403
    assert client.put('/api/v1/roles/'+roles['worker']['id'],headers=admin,json={'name':'worker','permissions':['animals:read','history:rectify']}).status_code==403
    user={'name':'Prueba','paternal_lastname':'Perfil','maternal_lastname':'Local','email':'profile.local@example.com','password':PASSWORD,'role_id':roles['worker']['id']}
    created=client.post('/api/v1/users',headers=admin,json=user)
    assert created.status_code==201,created.text;uid=created.json()['id'];session=login(client,user['email'])
    assert client.patch('/api/v1/users/'+uid,headers=owner,json={'role_id':roles['livestock_technician']['id']}).status_code==200
    assert client.get('/api/v1/auth/me',headers=session).status_code==401
    session=login(client,user['email'])
    assert client.get('/api/v1/auth/me',headers=session).json()['role_name']=='livestock_technician'
    assert client.delete('/api/v1/users/'+uid,headers=admin).status_code==204
    assert client.get('/api/v1/auth/me',headers=session).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':user['email'],'password':PASSWORD}).status_code==401
