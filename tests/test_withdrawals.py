from datetime import date
from sqlalchemy import select
from src.core.models import EventTreatmentModel, AuditModel
from src.features.health.infrastructure.withdrawals import treatment_estimate
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case
from tests.test_treatments import product
from tests.test_programs import program, application


def treatment(client, headers, animal_id, p, **values):
    case = create_case(client, headers, animal_id).json()
    response = client.post(f"/api/v1/health/cases/{case['id']}/treatments", headers=headers,
        json=dict(product_id=p['id'], start_date='2024-01-03', dose_value='2',
                  dose_unit_id=1, route_id=1, duration_days=3, **values))
    assert response.status_code == 201, response.text
    return response.json()


def check(client, headers, animal_id, day):
    response = client.get(f'/api/v1/exits/animals/{animal_id}/withdrawal',
                          headers=headers, params={'date':day})
    assert response.status_code == 200, response.text
    return response.json()


def test_snapshot_boundary_and_exit_audit(api):
    client, factory = api
    h = login(client)
    a = animal(client, h)
    p = product(client, h).json()
    t = treatment(client, h, a['id'], p)
    assert check(client, h, a['id'], '2024-01-12')['status'] == 'pending'
    assert check(client, h, a['id'], '2024-01-13')['status'] == 'complete'
    assert check(client, h, a['id'], '2024-01-02')['status'] == 'no_records'
    assert client.put('/api/v1/health/products/'+p['id'], headers=h, json={
        'name':p['name'], 'product_type_id':1, 'unit_id':1, 'withdrawal_days':0,
        'active':False}).status_code == 200
    assert check(client, h, a['id'], '2024-01-12')['release_date'] == '2024-01-13'
    response = client.post('/api/v1/exits', headers=h, json={
        'animal_id':a['id'], 'date':'2024-01-06', 'exit_type':'sale', 'reason':'Venta registrada'})
    assert response.status_code == 201, response.text
    with factory() as db:
        assert db.get(EventTreatmentModel, (t['id'], p['id'])).withdrawal_days == 7
        audit = db.scalar(select(AuditModel).where(AuditModel.record_id == response.json()['id']))
        assert audit.new_values['withdrawal']['status'] == 'pending'
    assert client.get('/api/v1/health/withdrawals',headers=h).json()['total'] == 0


def test_unknown_history_and_permissions(api):
    client, factory = api
    h = login(client)
    a = animal(client,h)
    p = product(client,h).json()
    t = treatment(client,h,a['id'],p)
    with factory() as db:
        db.get(EventTreatmentModel,(t['id'],p['id'])).withdrawal_days = None
        db.commit()
    summary = check(client,h,a['id'],'2024-02-01')
    assert summary['status'] == 'unknown' and summary['unknown_count'] == 1
    detail = client.get('/api/v1/health/animals/'+a['id']+'/withdrawal',headers=h).json()
    assert detail['items'][0]['withdrawal_days'] is None
    assert client.get('/api/v1/health/withdrawals?q=nomatch',headers=h).json()['total'] == 0
    worker = login(client,'worker@example.com')
    for path in ['/health/withdrawals','/health/animals/'+a['id']+'/withdrawal',
                 '/exits/animals/'+a['id']+'/withdrawal?date=2024-01-01']:
        assert client.get('/api/v1'+path,headers=worker).status_code == 403
        assert client.get('/api/v1'+path).status_code == 401


def test_program_snapshot_and_overflow(api):
    client,factory=api
    h=login(client)
    a=animal(client,h,birth_date='2024-01-01')
    p=product(client,h,withdrawal_days=2147483647).json()
    prog=program(client,h,p['id']).json()
    t=application(client,h,prog['id'],a['id']).json()
    with factory() as db:
        recorded=db.get(EventTreatmentModel,(t['id'],p['id']))
        assert recorded.withdrawal_days == 2147483647
        assert treatment_estimate(recorded,date.today())['status'] == 'unknown'
    assert check(client,h,a['id'],str(date.today()))['status'] == 'unknown'


def test_multiple_products_and_replaced_events(api):
    from datetime import datetime
    from src.core.models import EventModel
    client, factory = api
    h = login(client)
    a = animal(client, h)
    p = product(client, h, withdrawal_days=30).json()
    first = treatment(client, h, a['id'], p)
    other = product(client, h, name='Segundo producto', withdrawal_days=0).json()
    second = treatment(client, h, a['id'], other)
    assert check(client, h, a['id'], '2024-01-10')['release_date'] == '2024-02-05'
    with factory() as db:
        original = db.get(EventModel, first['id'])
        replacement = EventModel(animal_id=a['id'], event_type_id=1,
            date=datetime(2024,1,6), user_id=original.user_id, role_id=original.role_id,
            replaced_event_id=first['id'])
        db.add(replacement)
        db.commit()
    result = check(client, h, a['id'], '2024-01-10')
    assert result['treatment_count'] == 1 and result['status'] == 'complete'
    assert result['release_date'] == '2024-01-06'
    assert check(client,h,a['id'],'2024-01-05')['in_treatment']
