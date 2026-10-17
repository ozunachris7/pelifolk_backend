from datetime import date,timedelta
from sqlalchemy import select,func
from src.core.models import AnimalIncidentModel,IncidentFollowupModel,AuditModel,RoleModel,RolePermissionModel,HealthCaseModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case

URL='/api/v1/health/incidents'
def report(client,h,a,**changes):
    return client.post(URL,headers=h,json={'animal_id':a['id'],'date':'2024-01-04','kind':'accident','description':'Se observa una lesión tras un incidente reportado.',**changes})
def follow(client,h,r,**changes):
    return client.post(URL+'/'+r['id']+'/followups',headers=h,json={'date':'2024-01-05','expected_version':0,'status':'in_progress','notes':'Se documenta el seguimiento del incidente.',**changes})


def test_report_append_only_followups_close_reopen_and_stale_version(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    response=report(client,h,a,location='Corral norte',initial_actions='Se informó al encargado.');assert response.status_code==201,response.text;r=response.json()
    assert r['status']=='open' and r['version']==0 and r['recorded_by'].startswith('Owner')
    f=follow(client,h,r);assert f.status_code==201,f.text;d=f.json()
    assert d['incident']['status']=='in_progress' and d['incident']['description']==r['description']
    assert follow(client,h,r,status='closed').status_code==409
    assert follow(client,h,r,expected_version=1,date='2024-01-04').status_code==422
    closed=follow(client,h,r,expected_version=1,status='closed',date='2024-01-06',notes='Seguimiento finalizado.').json()
    assert closed['incident']['version']==2
    reopened=follow(client,h,r,expected_version=2,status='open',date='2024-01-07',notes='Se reabre para documentar nueva información.').json()
    assert reopened['incident']['status']=='open' and reopened['followups']['total']==3
    assert [i['version'] for i in reopened['followups']['items']]==[3,2,1]
    assert reopened['last_followup_date']=='2024-01-07'
    page=client.get(URL+'/'+r['id']+'?offset=1&limit=1',headers=h).json();assert page['followups']['items'][0]['version']==2
    assert page['incident']['description']==r['description']
    for method in ['put','delete']:assert getattr(client,method)(URL+'/'+r['id'],headers=h).status_code==405
    with factory() as db:
        assert db.get(AnimalIncidentModel,r['id']).role_id
        rows=db.scalars(select(IncidentFollowupModel)).all();assert len(rows)==3 and all(row.role_id for row in rows)
        assert db.scalar(select(func.count()).select_from(AuditModel).where(AuditModel.table=='incident_followups'))==3
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline?module=health',headers=h).json()['items']
    assert sum(i['kind']=='incident_followup' for i in timeline)==3
    assert next(i for i in timeline if i['kind']=='incident')['notes']==r['description']
    assert client.get('/api/v1/audit?module=health&table=incident_followups',headers=h).json()['total']==3


def test_links_are_same_animal_and_can_be_added_during_followup(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');other=animal(client,h,siniiga='INC-OTHER',birth_date='2020-01-01')
    c=create_case(client,h,a['id']).json();oc=create_case(client,h,other['id']).json()
    assert report(client,h,a,health_case_id=oc['id']).status_code==422
    r=report(client,h,a,health_case_id=c['id']).json();assert r['health_case']['id']==c['id']
    assert follow(client,h,r,health_case_id=oc['id']).status_code==422
    valid=follow(client,h,r,health_case_id=c['id']);assert valid.status_code==201,valid.text
    assert valid.json()['followups']['items'][0]['health_case']['id']==c['id']
    opts=client.get(URL+'/case-options',headers=h,params={'animal_id':a['id']}).json()
    assert [i['id'] for i in opts]==[c['id']]
    assert client.get(URL+'/case-options',headers=h,params={'animal_id':a['id'],'q':'%'}).json()==[]
    with api[1]() as db:assert db.get(HealthCaseModel,c['id']).status=='open'


def test_permissions_validation_and_filters(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a=animal(client,h,birth_date='2020-01-01')
    assert client.get(URL).status_code==401 and client.get(URL,headers=worker).status_code==403
    assert report(client,worker,a).status_code==403
    for values in ({'date':(date.today()+timedelta(days=1)).isoformat()},{'date':'2019-01-01'},{'description':' '},
                   {'kind':'invalid'},{'user_id':a['id']},{'health_case_id':a['id']}):
        assert report(client,h,a,**values).status_code==422,values
    male=animal(client,h,siniiga='INC-MALE',sex='male',birth_date='2020-01-01');assert report(client,h,male,kind='abortion').status_code==422
    r=report(client,h,a,kind='abortion').json()
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'male','birth_date':'2020-01-01'}).status_code==422
    assert client.get(URL,headers=h,params={'kind':'abortion','status':'open','q':a['siniiga']}).json()['total']==1
    assert client.get(URL+'?kind=attack',headers=h).json()['total']==0
    assert client.get(URL+'?limit=101',headers=h).status_code==422
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add(RolePermissionModel(role_id=role.id,permission='health:read'))
    assert client.get(URL,headers=worker).status_code==200 and follow(client,worker,r).status_code==403
    for values in ({'notes':' '},{'expected_version':-1},{'status':'bad'},{'date':'2024-01-03'},{'role_id':a['id']}):
        assert follow(client,h,r,**values).status_code==422


def test_incident_dates_preserve_birth_and_exit_without_automatic_exit(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');r=report(client,h,a,kind='disappearance').json()
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['status']=='active'
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-05'}).status_code==422
    exit_data={'animal_id':a['id'],'date':'2024-01-03','exit_type':'sale','reason':'Venta'}
    assert client.post('/api/v1/exits',headers=h,json=exit_data).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={**exit_data,'date':'2024-01-05'}).status_code==201
    assert report(client,h,a,date='2024-01-06').status_code==409
    # Follow-up is administrative history and can continue after the exit.
    assert follow(client,h,r,date='2024-01-06',status='closed').status_code==201


def test_incident_history_does_not_leak_through_animal_permission(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');r=report(client,h,a).json()
    assert follow(client,h,r).status_code==201
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        if not db.get(RolePermissionModel,(role.id,'animals:read')):
            db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    worker=login(client,'worker@example.com')
    result=client.get('/api/v1/animals/'+a['id']+'/timeline',headers=worker)
    assert result.status_code==200,result.text
    assert not any(i['kind'] in ('incident','incident_followup') for i in result.json()['items'])
    assert client.get(URL+'/'+r['id'],headers=worker).status_code==403
