from datetime import date
from sqlalchemy import select
from src.core.models import EventTreatmentModel
from src.features.health.infrastructure.withdrawals import animal_summary
from tests.conftest import login
from tests.test_doses import dose
from tests.test_health import create_case
from tests.test_animals import animal
from tests.test_treatments import product


def setup(client,h,duration=3,days=7):
    a=animal(client,h);c=create_case(client,h,a['id']).json();p=product(client,h,withdrawal_days=days).json()
    r=client.post('/api/v1/health/cases/'+c['id']+'/treatments',headers=h,json={'product_id':p['id'],'start_date':'2024-01-03','duration_days':duration,'dose_value':'2','dose_unit_id':1,'route_id':1})
    assert r.status_code==201,r.text
    return a,p,r.json()


def test_no_administrations_do_not_become_completed_withdrawal(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h)
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,2,1),True)
    assert result['status']=='unknown' and result['release_date'] is None and result['missing_applications_count']==1
    entry=result['items'][0]
    assert entry['planned_release_date']==date(2024,1,13) and entry['last_applied_at'] is None
    assert entry['review_reasons']==['missing_applications'] and entry['application_count']==0
    assert entry['estimated_release_date'] is None and entry['calculation_basis']=='planned'


def test_last_actual_instant_backdating_and_historical_dates(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h)
    assert dose(client,h,t,p,applied_at='2024-01-03T23:30:00-06:00').status_code==201
    assert dose(client,h,t,p,applied_at='2024-01-03T08:00:00-06:00').status_code==201
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,1,6),True)
    item=result['items'][0]
    assert item['last_applied_at']=='2024-01-03T23:30:00-06:00' and item['application_count']==2
    assert item['release_date']==date(2024,1,11) and item['planned_release_date']==date(2024,1,13)
    assert result['status']=='pending'
    assert dose(client,h,t,p,applied_at='2024-01-04T09:00:00-06:00').status_code==201
    with factory() as db:
        older=animal_summary(db,a['id'],date(2024,1,3),True)
        newer=animal_summary(db,a['id'],date(2024,1,12),True)
    assert older['application_count']==2 and older['items'][0]['estimated_release_date']==date(2024,1,11)
    assert older['in_treatment'] and older['release_date'] is None
    assert newer['status']=='complete' and newer['release_date']==date(2024,1,12)
    assert newer['items'][0]['application_count']==3


def test_variation_keeps_actual_reference_but_requires_review(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h)
    assert dose(client,h,t,p,applied_at='2024-01-07T10:00:00-06:00',notes='Fecha de aplicación fuera del periodo indicado.').status_code==201
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,2,1),True)
    entry=result['items'][0]
    assert result['status']=='unknown' and result['release_date'] is None
    assert entry['estimated_release_date']==date(2024,1,15) and 'dose_variation' in entry['review_reasons']
    assert entry['last_applied_at']=='2024-01-07T10:00:00-06:00'


def test_zero_days_and_ongoing_plan_do_not_imply_same_day_clearance(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h,duration=20,days=0)
    assert dose(client,h,t,p,applied_at='2024-01-03T10:00:00-06:00').status_code==201
    with factory() as db:
        active=animal_summary(db,a['id'],date(2024,1,10),True)
        ended=animal_summary(db,a['id'],date(2024,1,23),True)
    assert active['status']=='pending' and active['in_treatment'] and active['release_date'] is None
    assert active['items'][0]['estimated_release_date']==date(2024,1,4)
    assert ended['status']=='complete' and ended['release_date']==date(2024,1,4)


def test_product_composite_keys_and_unknown_records_dominate_summary(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h)
    other=product(client,h,name='Segundo producto',withdrawal_days=0).json()
    with factory.begin() as db:
        db.add(EventTreatmentModel(event_id=t['id'],product_id=other['id'],health_case_id=t['health_case_id'],dose_value=2,dose_unit_id=1,route_id=1,start_date=date(2024,1,3),duration_days=3,withdrawal_days=0))
    assert dose(client,h,t,p).status_code==201
    with factory() as db:
        mixed=animal_summary(db,a['id'],date(2024,1,20),True)
    assert mixed['status']=='unknown' and mixed['release_date'] is None and mixed['application_count']==1
    assert dose(client,h,t,other,applied_at='2024-01-05T10:00:00-06:00').status_code==201
    with factory() as db:
        known=animal_summary(db,a['id'],date(2024,1,6),True)
    assert known['release_date']==date(2024,1,11) and known['application_count']==2
    by_product={i['product_id']:i for i in known['items']}
    assert by_product[p['id']]['application_count']==by_product[other['id']]['application_count']==1
    # The saved period is authoritative, not the current product catalog.
    assert client.put('/api/v1/health/products/'+p['id'],headers=h,json={'name':p['name'],'product_type_id':1,'unit_id':1,'withdrawal_days':0}).status_code==200
    with factory() as db:assert animal_summary(db,a['id'],date(2024,1,6))['release_date']==date(2024,1,11)


def test_replaced_instruction_without_actual_doses_is_excluded(api):
    from src.core.models import EventModel
    client,factory=api;h=login(client);a,p,t=setup(client,h)
    observation=client.post('/api/v1/health/observations',headers=h,json={'animal_id':a['id'],'date':'2024-01-06','observation':'Registro que reemplaza la referencia anterior.'}).json()
    with factory.begin() as db:db.get(EventModel,observation['id']).replaced_event_id=t['id']
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,2,1),True)
    assert result['status']=='no_records' and result['treatment_count']==0 and result['items']==[]


def test_unusable_saved_periods_do_not_produce_release_dates(api):
    client,factory=api;h=login(client);a,p,t=setup(client,h,days=2147483647)
    assert dose(client,h,t,p).status_code==201
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,2,1),True)
    assert result['status']=='unknown' and result['release_date'] is None
    assert 'date_overflow' in result['items'][0]['review_reasons']
    with factory.begin() as db:db.get(EventTreatmentModel,(t['id'],p['id'])).withdrawal_days=-1
    with factory() as db:
        result=animal_summary(db,a['id'],date(2024,2,1),True)
    assert result['status']=='unknown' and result['release_date'] is None
    assert 'invalid_withdrawal_days' in result['items'][0]['review_reasons']
