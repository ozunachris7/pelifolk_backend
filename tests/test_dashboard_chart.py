from datetime import date, timedelta
from decimal import Decimal

from src.core.models import IncomeModel, ExpenseModel, IncomeCategoryModel, ExpenseCategoryModel
from tests.conftest import login


def test_monthly_chart_aggregates_full_range_and_keeps_empty_months(api):
    client, factory = api
    headers = login(client)
    # Use enough rows to exceed a list page.
    with factory.begin() as db:
        db.add_all([IncomeCategoryModel(id=1, name='Chart incomes'),
                    ExpenseCategoryModel(id=1, name='Chart expenses')])
        db.flush()
        db.add_all([
            IncomeModel(income_category_id=1, date=date(2024, 12, 10), amount=Decimal('0.10'))
            for _ in range(101)
        ])
        db.add_all([
            IncomeModel(income_category_id=1, date=date(2024, 12, 9), amount=999),
            IncomeModel(income_category_id=1, date=date(2025, 2, 3), amount=Decimal('200.25')),
            ExpenseModel(expense_category_id=1, date=date(2025, 2, 3), amount=Decimal('250.50')),
            ExpenseModel(expense_category_id=1, date=date(2025, 2, 4), amount=999),
        ])
    response = client.get('/api/v1/dashboard/finance-trend', headers=headers,
                          params={'date_from': '2024-12-10', 'date_to': '2025-02-03'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['date_from'] == '2024-12-10' and data['date_to'] == '2025-02-03'
    assert data['currency'] == 'MXN' and data['movement_count'] == 103
    assert data['income_total'] == '210.35' and data['expense_total'] == '250.50'
    assert data['items'] == [
        dict(month='2024-12', income_total='10.10', expense_total='0.00', balance='10.10', income_count=101, expense_count=0),
        dict(month='2025-01', income_total='0.00', expense_total='0.00', balance='0.00', income_count=0, expense_count=0),
        dict(month='2025-02', income_total='200.25', expense_total='250.50', balance='-50.25', income_count=1, expense_count=1),
    ]


def test_chart_defaults_validation_and_finance_permission(api):
    client, _ = api
    headers = login(client)
    url = '/api/v1/dashboard/finance-trend'
    data = client.get(url, headers=headers).json()
    assert data['date_to'] == date.today().isoformat()
    assert len(data['items']) == 6 and data['movement_count'] == 0
    assert all(row['income_total'] == row['expense_total'] == '0.00' for row in data['items'])
    for params in [
        {'date_from': '2025-02-01', 'date_to': '2025-01-31'},
        {'date_from': '2020-01-01', 'date_to': '2025-01-01'},
        {'date_to': (date.today() + timedelta(days=1)).isoformat()},
        {'date_from': 'invalid'},
    ]:
        assert client.get(url, headers=headers, params=params).status_code == 422
    assert client.get(url).status_code == 401
    assert client.get(url, headers=login(client, 'worker@example.com')).status_code == 403
    assert client.get(url, headers=headers, params={'date_from': '2024-01-01', 'date_to': '2025-12-31'}).status_code == 200
