from datetime import date, timedelta
from sqlalchemy import select, func
from src.core.models import RoleModel, RolePermissionModel, EventModel, AuditModel
from tests.conftest import login
from tests.test_animals import animal


def setup_gestation(client,h,male,name,remaining=None):
    a=animal(client,h,name=name,birth_date='2020-01-01');mating=None
    if remaining is not None:
        day=date.today()+timedelta(days=remaining-147)
        r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':a['id'],'male_id':male['id'],'date':str(day)})
        assert r.status_code==201,r.text;mating=r.json()
    r=client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':a['id'],'date':str(date.today()-timedelta(days=1)),'result':'pregnant','mating_event_id':mating['id'] if mating else None})
    assert r.status_code==201,r.text
    return a,mating,r.json()


def test_upcoming_estimates_boundaries_missing_links_and_filtered_totals(api):
    client,factory=api;h=login(client);male=animal(client,h,sex='male',birth_date='2019-01-01')
    for name,days in [('Pasada',-1),('Hoy',0),('Próxima',14),('Más adelante',15),('Sin monta',None)]:setup_gestation(client,h,male,name,days)
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    r=client.get('/api/v1/breeding/upcoming-births',headers=h,params={'limit':1});assert r.status_code==200,r.text
    page=r.json();assert page['total']==5 and len(page['items'])==1
    assert page['counts']=={'past_estimate':1,'due':1,'upcoming':1,'scheduled':1,'missing_mating':1}
    assert page['items'][0]['status']=='past_estimate' and page['items'][0]['days_remaining']==-1
    nearby=client.get('/api/v1/breeding/upcoming-births',headers=h,params={'status':'upcoming'}).json()
    assert nearby['total']==1 and nearby['items'][0]['expected_birth_date']==str(date.today()+timedelta(days=14))
    assert nearby['items'][0]['male']['id']==male['id']
    expanded=client.get('/api/v1/breeding/upcoming-births',headers=h,params={'status':'upcoming','notice_days':15}).json();assert expanded['total']==2
    missing=client.get('/api/v1/breeding/upcoming-births',headers=h,params={'status':'missing_mating'}).json()['items'][0]
    assert missing['expected_birth_date'] is None and missing['days_remaining'] is None and missing['missing_reason']=='unlinked'
    assert client.get('/api/v1/breeding/upcoming-births',headers=h,params={'q':'%'}).json()['total']==0
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before


def test_later_diagnoses_births_exits_and_replaced_matings(api):
    client,factory=api;h=login(client);male=animal(client,h,sex='male',birth_date='2019-01-01')
    vacia,_,_=setup_gestation(client,h,male,'Vacía',10)
    dudosa,_,_=setup_gestation(client,h,male,'Dudosa',10)
    birth,_,_=setup_gestation(client,h,male,'Con parto',10)
    exited,_,_=setup_gestation(client,h,male,'Vendida',10)
    replaced,old,_=setup_gestation(client,h,male,'Monta reemplazada',10)
    for a,result in [(vacia,'not_pregnant'),(dudosa,'uncertain')]:
        assert client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':a['id'],'date':str(date.today()),'result':result}).status_code==201
    assert client.post('/api/v1/breeding/births',headers=h,json={'animal_id':birth['id'],'date':str(date.today()),'birth_type_id':1,'offspring':[{'name':'Cría','sex':'female'}]}).status_code==201
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':exited['id'],'date':str(date.today()),'exit_type':'sale','reason':'Venta'}).status_code==201
    r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':replaced['id'],'male_id':male['id'],'date':old['date']});assert r.status_code==201
    with factory.begin() as db:db.get(EventModel,r.json()['id']).replaced_event_id=old['id']
    rows=client.get('/api/v1/breeding/upcoming-births',headers=h).json()['items']
    assert len(rows)==1 and rows[0]['animal']['id']==replaced['id']
    assert rows[0]['expected_birth_date'] is None and rows[0]['missing_reason']=='unavailable_mating'


def test_link_to_previous_cycle_has_no_estimated_date(api):
    client,_=api;h=login(client);male=animal(client,h,sex='male',birth_date='2019-01-01')
    a,mating,_=setup_gestation(client,h,male,'Ciclo anterior',-10)
    assert client.post('/api/v1/breeding/births',headers=h,json={'animal_id':a['id'],'date':str(date.today()-timedelta(days=1)),'birth_type_id':1,'offspring':[{'name':'Cría','sex':'female'}]}).status_code==201
    assert client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':a['id'],'date':str(date.today()),'result':'pregnant','mating_event_id':mating['id']}).status_code==201
    row=client.get('/api/v1/breeding/upcoming-births',headers=h).json()['items'][0]
    assert row['missing_reason']=='before_last_birth' and row['expected_birth_date'] is None


def test_upcoming_permissions_and_validation(api):
    client,factory=api;worker=login(client,'worker@example.com');path='/api/v1/breeding/upcoming-births'
    assert client.get(path).status_code==401 and client.get(path,headers=worker).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='breeding:read'))
    assert client.get(path,headers=worker).status_code==200
    for params in ({'notice_days':0},{'notice_days':61},{'status':'bad'},{'limit':101},{'offset':-1},{'q':'a'*101}):assert client.get(path,headers=worker,params=params).status_code==422
