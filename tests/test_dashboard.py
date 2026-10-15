from datetime import date, datetime, timedelta
from sqlalchemy import select
from src.core.models import EventModel, EventPregnancyModel, EventBirthModel, HealthCaseModel, RoleModel, RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal


def test_summary_counts_and_permission_isolation(api):
    client,factory=api;h=login(client)
    a=animal(client,h,birth_date='2020-01-01')
    response=client.get('/api/v1/dashboard/summary',headers=h)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['herd']==dict(total=1,active=1,exited=0,female=1,male=0)
    assert data['finance']['balance']==0 and data['feeding']['consumptions']==0
    assert data['activity']==[] and data['breeding']['pregnant']==0
    worker=login(client,'worker@example.com')
    private=client.get('/api/v1/dashboard/summary',headers=worker).json()
    assert all(private[key] is None for key in ('herd','health','breeding','finance','feeding'))
    assert private['activity']==[]
    assert client.get('/api/v1/dashboard/summary').status_code==401
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    limited=client.get('/api/v1/dashboard/summary',headers=worker).json()
    assert limited['herd']['active']==1 and limited['finance'] is None


def test_summary_current_pregnancy_cases_and_activity(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    # Use valid events through API; the later birth closes the diagnosed pregnancy.
    r=client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':a['id'],'date':date.today().isoformat(),'result':'pregnant'})
    assert r.status_code==201,r.text
    with factory.begin() as db:
        db.add(HealthCaseModel(animal_id=a['id'],reason='Seguimiento',status='under_treatment',start_date=date.today()))
    data=client.get('/api/v1/dashboard/summary',headers=h).json()
    assert data['breeding']['pregnant']==1
    assert data['health']['treatment_cases']==1
    assert data['activity'][0]['type_id']==6
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':date.today().isoformat(),'exit_type':'sale','reason':'Venta'}).status_code==201
    data=client.get('/api/v1/dashboard/summary',headers=h).json()
    assert data['herd']['active']==0 and data['herd']['exited']==1
    assert data['breeding']['pregnant']==0


def test_summary_monthly_finance_feeding_and_birth_closes_pregnancy(api):
    from src.core.models import IncomeCategoryModel, ExpenseCategoryModel, IncomeModel, ExpenseModel, FeedModel, FeedPriceModel, FeedingModel, UserModel
    from decimal import Decimal
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    today=date.today();start=today.replace(day=1);previous=start-timedelta(days=1)
    with factory.begin() as db:
        ic=IncomeCategoryModel(name='sales');ec=ExpenseCategoryModel(name='supplies');db.add_all([ic,ec]);db.flush()
        db.add_all([IncomeModel(income_category_id=ic.id,amount=100,date=today),ExpenseModel(expense_category_id=ec.id,amount=30,date=today),ExpenseModel(expense_category_id=ec.id,amount=500,date=previous)])
        feed=FeedModel(name='Concentrado',unit_id=1);db.add(feed);db.flush()
        db.add(FeedPriceModel(feed_id=feed.id,effective_from=previous,unit_cost=Decimal('8.5')))
        db.add_all([FeedingModel(feed_id=feed.id,animal_id=a['id'],date=today,quantity=2),FeedingModel(feed_id=feed.id,animal_id=a['id'],date=previous,quantity=10)])
        owner=db.scalar(select(UserModel).where(UserModel.email=='owner@example.com'))
        diagnosis=EventModel(animal_id=a['id'],event_type_id=6,date=datetime.combine(previous,datetime.min.time()),user_id=owner.id,role_id=owner.role_id)
        birth=EventModel(animal_id=a['id'],event_type_id=7,date=datetime.combine(today,datetime.min.time()),user_id=owner.id,role_id=owner.role_id)
        db.add_all([diagnosis,birth]);db.flush()
        db.add_all([EventPregnancyModel(event_id=diagnosis.id,result='pregnant'),EventBirthModel(event_id=birth.id,birth_type_id=1)])
    data=client.get('/api/v1/dashboard/summary',headers=h).json()
    assert data['finance']['balance']==70
    assert data['feeding']==dict(consumptions=1,cost='17.00',unpriced_count=0)
    assert data['breeding']==dict(pregnant=0,births=1)
