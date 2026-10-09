from datetime import date,timedelta,datetime
from sqlalchemy import select,func
from src.core.models import AuditModel,EventModel,EventTypeModel,ExitModel
from src.features.health.domain.schedule import next_application
from tests.conftest import login
from tests.test_animals import animal
from tests.test_treatments import product


def program(client,headers,product_id,**values):
    return client.post('/api/v1/health/programs',headers=headers,json={'name':'Control sanitario','product_id':product_id,'interval_days':90,'minimum_age_days':30,'notice_days':7,**values})


def application(client,headers,program_id,animal_id,**values):
    return client.post('/api/v1/health/programs/'+program_id+'/applications',headers=headers,json={'animal_id':animal_id,'start_date':str(date.today()),'dose_value':'2.125','dose_unit_id':1,'route_id':1,'duration_days':1,**values})


def test_next_dates_and_notice_boundaries():
    today=date(2024,3,1)
    assert next_application(date(2024,1,1),60,None,90,7,today)==(today,0,'due')
    assert next_application(date(2024,1,1),59,None,90,7,today)[2]=='overdue'
    assert next_application(date(2024,1,1),67,None,90,7,today)[2]=='upcoming'
    assert next_application(date(2024,1,1),68,None,90,7,today)[2]=='scheduled'
    assert next_application(None,30,None,90,7,today)[2]=='missing_birth_date'
    assert next_application(None,0,date(2024,2,28),3,0,today)[0]==date(2024,3,2)


def test_program_lifecycle_applications_schedule_and_history(api):
    client,factory=api;owner=login(client);today=date.today()
    p=product(client,owner).json();saved=animal(client,owner,birth_date=str(today-timedelta(days=365)),siniiga='MXP1')
    response=program(client,owner,p['id'],sex='female');assert response.status_code==201,response.text
    prog=response.json();base='/api/v1/health/programs/'+prog['id']
    schedule=client.get(base+'/schedule',headers=owner).json();assert schedule['items'][0]['status']=='overdue' and schedule['items'][0]['can_apply']
    assert program(client,owner,p['id'],name=' control sanitario ').status_code==409
    response=application(client,owner,prog['id'],saved['id']);assert response.status_code==201,response.text
    treatment=response.json();assert treatment['program_id']==prog['id'] and treatment['health_case_id'] is None
    assert treatment['program_name']=='Control sanitario'
    assert application(client,owner,prog['id'],saved['id']).status_code==409
    assert client.get(base+'/schedule',headers=owner).json()['total']==0
    item=client.get(base+'/schedule?state=all&q=mxp1',headers=owner).json()['items'][0]
    assert item['due_date']==str(today+timedelta(days=90)) and item['last_application']==str(today) and item['status']=='scheduled'
    history=client.get('/api/v1/health/animals/'+saved['id']+'/history',headers=owner).json();assert history['treatments'][0]['id']==treatment['id']
    other=product(client,owner,name='Other product').json()
    update={'name':'Control editado','product_id':p['id'],'interval_days':60,'minimum_age_days':30,'sex':'female','notice_days':5,'active':True}
    assert client.put(base,headers=owner,json={**update,'product_id':other['id']}).status_code==409
    assert client.put(base,headers=owner,json=update).status_code==200
    assert client.get(base+'/schedule?state=all',headers=owner).json()['items'][0]['due_date']==str(today+timedelta(days=60))
    assert client.put(base,headers=owner,json={**update,'active':False}).status_code==200
    assert client.get('/api/v1/health/programs?active=true',headers=owner).json()['total']==0
    assert application(client,owner,prog['id'],saved['id'],start_date=str(today-timedelta(days=1))).status_code==409
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==treatment['id']));assert audit.new_values['program_id']==prog['id']


def test_age_sex_missing_birth_exit_and_permissions(api):
    client,factory=api;owner,worker=login(client),login(client,'worker@example.com');today=date.today();p=product(client,owner).json();prog=program(client,owner,p['id'],sex='female').json()
    young=animal(client,owner,name='Young',birth_date=str(today-timedelta(days=23)))
    unknown=animal(client,owner,name='Unknown')
    male=animal(client,owner,name='Male',sex='male',birth_date=str(today-timedelta(days=365)))
    old=animal(client,owner,name='Old',birth_date=str(today-timedelta(days=365)))
    assert client.get('/api/v1/health/programs',headers=worker).status_code==403
    assert client.get('/api/v1/health/programs/'+prog['id']+'/schedule',headers=worker).status_code==403
    assert program(client,worker,p['id']).status_code==403
    assert application(client,worker,prog['id'],old['id']).status_code==403
    assert application(client,owner,prog['id'],young['id']).status_code==422
    assert application(client,owner,prog['id'],unknown['id']).status_code==422
    assert application(client,owner,prog['id'],male['id']).status_code==422
    with factory.begin() as db:
        actor=db.scalar(select(AuditModel.user_id).where(AuditModel.table=='health_programs'))
        role=db.scalar(select(EventModel.role_id))
        from src.core.models import UserModel
        user=db.get(UserModel,actor)
        if not db.get(EventTypeModel,8):db.add(EventTypeModel(id=8,code='exit',name='Exit'))
        db.flush();event=EventModel(animal_id=old['id'],event_type_id=8,date=datetime.combine(today-timedelta(days=1),datetime.min.time()),user_id=user.id,role_id=user.role_id);db.add(event);db.flush();db.add(ExitModel(event_id=event.id,event_type_id=8,exit_type='sale'))
    items=client.get('/api/v1/health/programs/'+prog['id']+'/schedule?state=all',headers=owner).json()['items']
    assert {i['animal']['name'] for i in items}=={'Young','Unknown'}
    assert next(i for i in items if i['animal']['name']=='Young')['status']=='upcoming'
    assert next(i for i in items if i['animal']['name']=='Unknown')['status']=='missing_birth_date'
    assert all(not i['can_apply'] for i in items)
    assert application(client,owner,prog['id'],old['id']).status_code==409
    assert application(client,owner,prog['id'],old['id'],start_date=str(today+timedelta(days=1))).status_code==422
    assert program(client,owner,p['id'],interval_days=0).status_code==422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EventModel).where(EventModel.event_type_id==3))==0
