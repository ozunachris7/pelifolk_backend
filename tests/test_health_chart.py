from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import HealthCaseModel
from tests.conftest import login
from tests.test_animals import animal


def test_health_trend_exact_dates_full_history_and_reopened_cases(api):
    client, factory = api
    headers = login(client)
    a = animal(client, headers, birth_date='2020-01-01')
    with factory.begin() as db:
        for i in range(101):
            db.add(HealthCaseModel(animal_id=a['id'], reason=f'Case {i}', start_date=date(2024,12,10),status='open'))
        db.add_all([
            HealthCaseModel(animal_id=a['id'],reason='Starts before, closes within',start_date=date(2024,12,9),status='closed',closed_date=date(2025,2,3)),
            HealthCaseModel(animal_id=a['id'],reason='Starts and closes within',start_date=date(2024,12,11),status='closed',closed_date=date(2024,12,31)),
            HealthCaseModel(animal_id=a['id'],reason='Close beyond end',start_date=date(2025,2,3),status='closed',closed_date=date(2025,2,4)),
            HealthCaseModel(animal_id=a['id'],reason='Reopen target',start_date=date(2024,12,12),status='closed',closed_date=date(2025,2,3)),
            HealthCaseModel(animal_id=a['id'],reason='Outside',start_date=date(2025,2,4),status='open'),
        ])
    params={'date_from':'2024-12-10','date_to':'2025-02-03'}
    url='/api/v1/dashboard/health-trend'
    data=client.get(url,headers=headers,params=params).json()
    assert data['items']==[dict(month='2024-12',started=103,closed=1),dict(month='2025-01',started=0,closed=0),dict(month='2025-02',started=1,closed=2)]
    assert data['started_total']==104 and data['closed_total']==3 and data['event_count']==107
    with factory.begin() as db:
        row=db.scalar(select(HealthCaseModel).where(HealthCaseModel.reason=='Reopen target'))
        case_id=row.id
    reopened=client.patch(f'/api/v1/health/cases/{case_id}/status',headers=headers,json={'expected_status':'closed','status':'open','closed_date':None})
    assert reopened.status_code==200,reopened.text
    data=client.get(url,headers=headers,params=params).json()
    assert data['started_total']==104 and data['closed_total']==2
    assert data['items'][2]==dict(month='2025-02',started=1,closed=1)


def test_health_trend_defaults_permissions_and_validation(api):
    client,_=api;headers=login(client);url='/api/v1/dashboard/health-trend'
    data=client.get(url,headers=headers).json()
    assert data['date_to']==date.today().isoformat()
    assert len(data['items'])==6 and data['event_count']==0
    assert client.get(url).status_code==401
    assert client.get(url,headers=login(client,'worker@example.com')).status_code==403
    for params in [dict(date_from='2025-02-01',date_to='2025-01-01'),dict(date_from='2020-01-01',date_to='2025-01-01'),dict(date_to=(date.today()+timedelta(days=1)).isoformat()),dict(date_from='bad')]:
        assert client.get(url,headers=headers,params=params).status_code==422
    assert client.get(url,headers=headers,params=dict(date_from='2024-01-01',date_to='2025-12-31')).status_code==200
