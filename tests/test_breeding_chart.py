from datetime import date, datetime, timedelta
from sqlalchemy import select
from src.core.models import (AnimalModel, BirthOffspringModel, EventModel, EventMatingModel,
    EventBirthModel, EventPregnancyModel, UserModel)
from tests.conftest import login
from tests.test_animals import animal


def test_reproductive_chart_counts_effective_events_not_offspring_or_list_pages(api):
    client, factory = api
    headers = login(client)
    female = animal(client, headers, birth_date='2020-01-01')
    male = animal(client, headers, name='Sire', sex='male', birth_date='2020-01-01')
    with factory.begin() as db:
        owner = db.scalar(select(UserModel).where(UserModel.email == 'owner@example.com'))
        def event(kind, timestamp, replacing=None):
            row = EventModel(animal_id=female['id'], event_type_id=kind,
                date=datetime.fromisoformat(timestamp), user_id=owner.id, role_id=owner.role_id,
                replaced_event_id=replacing)
            db.add(row); db.flush()
            if kind == 5:
                db.add(EventMatingModel(event_id=row.id, male_id=male['id']))
            elif kind == 7:
                db.add(EventBirthModel(event_id=row.id, birth_type_id=1))
            else:
                db.add(EventPregnancyModel(event_id=row.id, result='pregnant'))
            db.flush()
            return row
        event(5, '2024-12-09T23:59:59')  # Before the exact requested period.
        old = event(5, '2024-12-10T00:00:00')
        event(5, '2025-02-03T23:59:59', old.id)  # Moves the count to a different month.
        first = event(5, '2024-12-11T00:00:00')
        middle = event(5, '2024-12-12T00:00:00', first.id)
        event(5, '2024-12-13T00:00:00', middle.id)
        for index in range(101):
            event(5, f'2024-12-14T00:{index // 60:02d}:{index % 60:02d}')
        birth = event(7, '2024-12-15T00:00:00')
        old_birth = event(7, '2024-12-20T00:00:00')
        event(7, '2025-02-03T00:00:00', old_birth.id)
        event(7, '2025-02-03T23:59:59')
        event(7, '2025-02-04T00:00:00')  # After the requested period.
        event(6, '2025-01-15T00:00:00')  # Pregnancy diagnoses do not count as matings or births.
        for name in ('Twin A', 'Twin B'):
            child = AnimalModel(name=name, sex='female', origin='born_in_herd',
                birth_date=date(2024, 12, 15), mother_id=female['id'], father_id=male['id'])
            db.add(child); db.flush()
            db.add(BirthOffspringModel(event_id=birth.id, animal_id=child.id, alive=True))
    response = client.get('/api/v1/dashboard/breeding-trend', headers=headers,
        params={'date_from': '2024-12-10', 'date_to': '2025-02-03'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['items'] == [dict(month='2024-12', matings=102, births=1),
        dict(month='2025-01', matings=0, births=0), dict(month='2025-02', matings=1, births=2)]
    assert data['matings_total'] == 103 and data['births_total'] == 3
    assert data['event_count'] == 106
    assert data['date_from'] == '2024-12-10' and data['date_to'] == '2025-02-03'


def test_reproductive_chart_defaults_permissions_and_date_validation(api):
    client, _ = api
    headers = login(client)
    url = '/api/v1/dashboard/breeding-trend'
    data = client.get(url, headers=headers).json()
    assert data['date_to'] == date.today().isoformat()
    assert len(data['items']) == 6 and data['event_count'] == 0
    assert all(row['matings'] == row['births'] == 0 for row in data['items'])
    assert client.get(url).status_code == 401
    assert client.get(url, headers=login(client, 'worker@example.com')).status_code == 403
    for params in [dict(date_from='2025-02-01', date_to='2025-01-01'),
        dict(date_from='2020-01-01', date_to='2025-01-01'),
        dict(date_to=(date.today() + timedelta(days=1)).isoformat()), dict(date_from='invalid')]:
        assert client.get(url, headers=headers, params=params).status_code == 422
    assert client.get(url, headers=headers, params=dict(date_from='2024-01-01', date_to='2025-12-31')).status_code == 200
