from datetime import date, timedelta
from decimal import Decimal
from src.core.models import FeedingModel, UnitModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_feeding import feed_setup


def test_feeding_chart_historical_prices_rounding_units_and_full_history(api):
    client, factory = api
    headers = login(client)
    feed = feed_setup(client, factory, headers)
    a = animal(client, headers, birth_date='2020-01-01')
    group = client.post('/api/v1/groups', headers=headers, json={'name': 'Flock'}).json()
    for start, cost in [('2024-01-01', '10.1250'), ('2024-03-01', '12.5000')]:
        response = client.post(f"/api/v1/feeding/feeds/{feed['id']}/prices", headers=headers,
            json={'effective_from': start, 'unit_cost': cost})
        assert response.status_code == 201, response.text
    with factory.begin() as db:
        db.add(UnitModel(id=3, code='bag'))
    bag = client.post('/api/v1/feeding/feeds', headers=headers, json={'name': 'Concentrate',
        'unit_id': 3, 'initial_price': {'effective_from': '2023-01-01', 'unit_cost': '0'}}).json()
    with factory.begin() as db:
        records = [('2023-12-30', '5', feed['id'], a['id'], None),  # Outside start.
            ('2023-12-31', '3', feed['id'], a['id'], None),  # Legacy missing price.
            ('2024-01-31', '1.25', feed['id'], a['id'], None),
            ('2024-03-01', '2', feed['id'], a['id'], None),
            ('2024-03-01', '1.50', bag['id'], None, group['id']),  # Free is known, not missing.
            ('2024-03-02', '8', feed['id'], a['id'], None)]  # Outside end.
        records += [('2024-01-31', '0.01', feed['id'], a['id'], None)] * 101
        for day, quantity, feed_id, animal_id, group_id in records:
            db.add(FeedingModel(date=date.fromisoformat(day), quantity=Decimal(quantity),
                feed_id=feed_id, animal_id=animal_id, group_id=group_id))
    response = client.get('/api/v1/dashboard/feeding-trend', headers=headers,
        params={'date_from': '2023-12-31', 'date_to': '2024-03-01'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['consumption_count'] == 105 and data['unpriced_count'] == 1
    assert data['total_cost'] == '47.76'  # 12.66 + 101 * 0.10 + 25.00, rounded per consumption.
    assert data['quantities'] == [{'unit_code': 'bag', 'quantity': '1.50'}, {'unit_code': 'kg', 'quantity': '7.26'}]
    assert data['items'] == [
        dict(month='2023-12', total_cost='0.00', consumption_count=1, unpriced_count=1,
             quantities=[dict(unit_code='kg', quantity='3.00')]),
        dict(month='2024-01', total_cost='22.76', consumption_count=102, unpriced_count=0,
             quantities=[dict(unit_code='kg', quantity='2.26')]),
        dict(month='2024-02', total_cost='0.00', consumption_count=0, unpriced_count=0, quantities=[]),
        dict(month='2024-03', total_cost='25.00', consumption_count=2, unpriced_count=0,
             quantities=[dict(unit_code='bag', quantity='1.50'), dict(unit_code='kg', quantity='2.00')])]
    assert data['date_from'] == '2023-12-31' and data['date_to'] == '2024-03-01'
    # Exact cost and quantities agree with the existing full-period feeding report.
    report = client.get('/api/v1/reports/feeding', headers=headers,
        params={'date_from': '2023-12-31', 'date_to': '2024-03-01', 'limit': 1}).json()
    assert report['total_cost'] == data['total_cost'] and report['quantities'] == data['quantities']


def test_feeding_chart_defaults_permissions_and_validation(api):
    client, _ = api
    headers = login(client)
    url = '/api/v1/dashboard/feeding-trend'
    data = client.get(url, headers=headers).json()
    assert data['date_to'] == date.today().isoformat()
    assert len(data['items']) == 6 and data['consumption_count'] == data['unpriced_count'] == 0
    assert data['total_cost'] == '0.00' and data['quantities'] == []
    assert client.get(url).status_code == 401
    assert client.get(url, headers=login(client, 'worker@example.com')).status_code == 403
    for params in [dict(date_from='2025-02-01', date_to='2025-01-01'),
        dict(date_from='2020-01-01', date_to='2025-01-01'),
        dict(date_to=(date.today() + timedelta(days=1)).isoformat()), dict(date_from='invalid')]:
        assert client.get(url, headers=headers, params=params).status_code == 422
    assert client.get(url, headers=headers, params=dict(date_from='2024-01-01', date_to='2025-12-31')).status_code == 200
