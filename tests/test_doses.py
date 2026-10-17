from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select,func
from src.core.models import AuditModel,EventModel,EventTreatmentModel,TreatmentDoseModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case,transition
from tests.test_treatments import product


def setup(client,h):
    a=animal(client,h,birth_date='2020-01-01');c=create_case(client,h,a['id']).json();p=product(client,h).json()
    r=client.post('/api/v1/health/cases/'+c['id']+'/treatments',headers=h,json={'product_id':p['id'],'start_date':'2024-01-03','dose_value':'2','dose_unit_id':1,'route_id':1,'duration_days':1})
    assert r.status_code==201,r.text
    return a,c,p,r.json()


def path(t,p):return '/api/v1/health/treatments/'+t['id']+'/products/'+p['id']+'/doses'


def dose(client,h,t,p,**changes):
    return client.post(path(t,p),headers=h,json={'applied_at':'2024-01-03T23:30:00-06:00','administered_by':'Veterinario responsable','dose_value':'2','dose_unit_id':1,'route_id':1,**changes})


def test_actual_dose_separates_responsible_and_recorder_preserves_local_date(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h)
    assert client.get(path(t,p),headers=h).json()['total']==0
    r=dose(client,h,t,p);assert r.status_code==201,r.text;d=r.json()
    assert d['applied_at']=='2024-01-03T23:30:00-06:00' and d['administered_by']=='Veterinario responsable'
    assert d['recorded_by'].startswith('Owner') and d['dose_value']=='2.000' and not d['is_deviation']
    assert dose(client,h,t,p,applied_at='2024-01-04T05:30:00Z').status_code==409
    listing=client.get(path(t,p),headers=h).json();assert listing['total']==1 and listing['items'][0]==d
    with factory() as db:
        row=db.get(TreatmentDoseModel,d['id']);assert row.clinical_date.isoformat()=='2024-01-03' and row.applied_at_utc==datetime(2024,1,4,5,30)
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='treatment_doses'))
        assert audit.new_values['administered_by']==d['administered_by'] and audit.new_values['role_id']
        assert db.get(EventTreatmentModel,(t['id'],p['id'])).dose_value==Decimal('2')
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline',headers=h,params={'module':'health','date_from':'2024-01-03','date_to':'2024-01-03'}).json()
    application=next(i for i in timeline['items'] if i['kind']=='dose')
    assert application['date']=='2024-01-03' and {'label':'Aplicada por','value':'Veterinario responsable'} in application['details']
    assert client.get('/api/v1/audit?module=health&table=treatment_doses',headers=h).json()['total']==1
    for method in ('put','delete'):assert getattr(client,method)(path(t,p),headers=h).status_code==405


def test_variations_require_explanation_and_protect_closure_exit_and_withdrawal(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h)
    assert dose(client,h,t,p,applied_at='2024-01-05T10:00:00-06:00').status_code==422
    result=dose(client,h,t,p,applied_at='2024-01-05T10:00:00-06:00',dose_value='1.5',notes='Se registra la cantidad y fecha realmente aplicadas.')
    assert result.status_code==201,result.text;assert result.json()['is_deviation']
    assert transition(client,h,c['id'],'under_treatment','closed',closed_date='2024-01-04').status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-01-04','exit_type':'sale','reason':'Venta'}).status_code==422
    # Do not present the old planned release date as established after a recorded variation.
    from src.features.health.infrastructure.withdrawals import animal_summary
    with factory() as db:
        assert animal_summary(db,a['id'],datetime(2024,1,20).date())['status']=='unknown'
    assert transition(client,h,c['id'],'under_treatment','closed',closed_date='2024-01-05').status_code==200
    assert dose(client,h,t,p,applied_at='2024-01-03T10:00:00-06:00').status_code==409
    with factory() as db:assert db.get(EventTreatmentModel,(t['id'],p['id'])).dose_value==Decimal('2')


def test_permissions_invalid_inputs_and_replaced_treatment(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a,c,p,t=setup(client,h)
    assert client.get(path(t,p)).status_code==401 and client.get(path(t,p),headers=worker).status_code==403
    assert dose(client,worker,t,p).status_code==403
    for values in ({'applied_at':'2024-01-03T10:00:00'}, {'applied_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
                   {'dose_value':'0'},{'dose_value':'1.2345'},{'administered_by':' '},{'user_id':'fake'},
                   {'applied_at':'2023-12-31T10:00:00Z'},{'dose_unit_id':999}):
        assert dose(client,h,t,p,**values).status_code==422
    with factory() as db:assert db.scalar(select(func.count()).select_from(TreatmentDoseModel))==0
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='health:read'))
    assert client.get(path(t,p),headers=worker).status_code==200 and dose(client,worker,t,p).status_code==403
    assert client.get(path(t,p)+'?limit=101',headers=h).status_code==422
    fake={**p,'id':a['id']};assert dose(client,h,t,fake).status_code==404
    with factory.begin() as db:
        old=db.get(EventModel,t['id']);db.add(EventModel(animal_id=a['id'],event_type_id=3,date=old.date,user_id=old.user_id,role_id=old.role_id,replaced_event_id=old.id))
    assert dose(client,h,t,p).status_code==409


def test_program_dose_can_be_historical_without_inventing_a_case(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');p=product(client,h).json()
    program=client.post('/api/v1/health/programs',headers=h,json={'name':'Programa registrado','product_id':p['id'],'interval_days':90}).json()
    r=client.post('/api/v1/health/programs/'+program['id']+'/applications',headers=h,json={'animal_id':a['id'],'start_date':'2024-01-03','dose_value':'2','dose_unit_id':1,'route_id':1,'duration_days':1})
    assert r.status_code==201,r.text;t=r.json()
    assert dose(client,h,t,p,applied_at='2024-01-02T10:00:00-06:00',notes='Fecha real anterior a la pauta capturada.').status_code==201
    from src.features.health.infrastructure.withdrawals import animal_summary
    with api[1]() as db:assert animal_summary(db,a['id'],datetime(2024,1,2).date())['status']=='unknown'
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-03'}).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-01-04','exit_type':'sale','reason':'Venta'}).status_code==201
    assert dose(client,h,t,p,applied_at='2024-01-05T10:00:00-06:00',notes='Registro posterior').status_code==409


def test_two_products_in_one_treatment_keep_separate_ledgers(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h)
    other=product(client,h,name='Otro producto').json()
    with factory.begin() as db:
        db.add(EventTreatmentModel(event_id=t['id'],product_id=other['id'],health_case_id=c['id'],
            dose_value=Decimal('2'),dose_unit_id=1,route_id=1,start_date=datetime(2024,1,3).date(),
            duration_days=1,withdrawal_days=7))
    assert dose(client,h,t,p).status_code==201
    assert dose(client,h,t,other).status_code==201
    first=client.get(path(t,p),headers=h).json();second=client.get(path(t,other),headers=h).json()
    assert first['total']==second['total']==1
    assert first['items'][0]['product_id']==p['id'] and second['items'][0]['product_id']==other['id']
    assert first['items'][0]['id']!=second['items'][0]['id']
