"""Real MySQL concurrency and representative-volume checks; explicit opt-in only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
from decimal import Decimal
from threading import Barrier,Lock
from time import perf_counter
from uuid import uuid4
import json
import pytest
from sqlalchemy import event,select,func,insert
from src.core import models as m
from tests.conftest import login
from tests.test_animals import animal
from tests.test_doses import setup,path,dose
from tests.test_incidents import report,follow
from tests.test_rectifications import entry,context,save


@pytest.fixture
def mysql_api(request):
    if not request.config.getoption('--mysql-api'):
        pytest.skip('Requires --mysql-api and an explicit isolated MySQL test server')
    return request.getfixturevalue('api')


def simultaneous_authenticated_requests(client,factory,calls):
    """Both auth reads finish before either mutation; each request owns a DB session."""
    gate=Barrier(2);lock=Lock();remaining=2
    def synchronize_auth(conn,cursor,statement,parameters,context,executemany):
        nonlocal remaining
        if not statement.lstrip().upper().startswith('SELECT') or 'FROM users' not in statement:
            return
        with lock:
            if remaining<=0:return
            remaining-=1
        gate.wait(timeout=10)
    engine=factory.kw['bind']
    event.listen(engine,'after_cursor_execute',synchronize_auth)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(call) for call in calls]
            results=[f.result(timeout=30) for f in futures]
        assert remaining==0,'Both independent authentication reads must overlap'
        return results
    finally:
        event.remove(engine,'after_cursor_execute',synchronize_auth)


def assert_one_conflict(results,success=201):
    assert sorted(r.status_code for r in results)==[success,409],[(r.status_code,r.text) for r in results]


def test_mysql_concurrent_daily_weights_cannot_duplicate(mysql_api):
    client,factory=mysql_api;owner=login(client);admin=login(client,'administrator@example.com');a=animal(client,owner,birth_date='2020-01-01')
    body={'animal_id':a['id'],'date':'2024-01-02','weight_kg':'25','notes':'SIMULACIÓN de capturas simultáneas.'}
    results=simultaneous_authenticated_requests(client,factory,[lambda:client.post('/api/v1/weights',headers=owner,json=body),lambda:client.post('/api/v1/weights',headers=admin,json=body)])
    assert_one_conflict(results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.EventWeightModel))==1
    assert client.get('/api/v1/weights/animals/'+a['id']+'/history',headers=owner).json()['items'][0]['weight_kg']=='25.00'


def test_mysql_concurrent_assignments_cannot_put_animal_in_two_groups(mysql_api):
    client,factory=mysql_api;owner=login(client);admin=login(client,'administrator@example.com');a=animal(client,owner,birth_date='2020-01-01')
    groups=[client.post('/api/v1/groups',headers=owner,json={'name':name}).json() for name in ['Primero','Segundo']]
    body={'animal_ids':[a['id']],'effective_date':'2024-01-02'}
    results=simultaneous_authenticated_requests(client,factory,[lambda:client.post('/api/v1/groups/'+groups[0]['id']+'/assignments',headers=owner,json=body),lambda:client.post('/api/v1/groups/'+groups[1]['id']+'/assignments',headers=admin,json=body)])
    assert_one_conflict(results)
    with factory() as db:assert db.scalar(select(func.count()).select_from(m.GroupAnimalModel).where(m.GroupAnimalModel.animal_id==a['id']))==1


def test_mysql_concurrent_actual_doses_cannot_duplicate(mysql_api):
    client,factory=mysql_api;owner=login(client);admin=login(client,'administrator@example.com');a,c,p,t=setup(client,owner)
    results=simultaneous_authenticated_requests(client,factory,[lambda:dose(client,owner,t,p),lambda:dose(client,admin,t,p)])
    assert_one_conflict(results)
    with factory() as db:assert db.scalar(select(func.count()).select_from(m.TreatmentDoseModel))==1


def test_mysql_concurrent_rectifications_preserve_one_successful_version(mysql_api):
    client,factory=mysql_api;owner=login(client);a=animal(client,owner,birth_date='2020-01-01')
    e=entry(client,owner,a,'Alta en el sistema');c=context(client,owner,a,e).json()
    results=simultaneous_authenticated_requests(client,factory,[lambda:save(client,owner,a,e,c,mode='clarification',clarification='Primera aclaración simultánea con la misma versión.'),lambda:save(client,owner,a,e,c,mode='clarification',clarification='Segunda aclaración simultánea con la misma versión.')])
    assert_one_conflict(results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.HistoryRectificationModel))==1
        assert db.scalar(select(func.count()).select_from(m.AuditModel).where(m.AuditModel.table=='history_rectifications'))==1


def test_mysql_concurrent_incident_followups_preserve_one_version(mysql_api):
    client,factory=mysql_api;owner=login(client);admin=login(client,'administrator@example.com');a=animal(client,owner,birth_date='2020-01-01')
    incident=report(client,owner,a).json()
    results=simultaneous_authenticated_requests(client,factory,[lambda:follow(client,owner,incident),lambda:follow(client,admin,incident)])
    assert_one_conflict(results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(m.IncidentFollowupModel))==1
        assert db.get(m.AnimalIncidentModel,incident['id']).version==1


def test_mysql_volume_pagination_totals_and_query_budgets(mysql_api,tmp_path):
    client,factory=mysql_api;owner=login(client)
    me=client.get('/api/v1/auth/me',headers=owner).json()
    ids=[str(uuid4()) for _ in range(1000)];groups=[str(uuid4()) for _ in range(10)]
    day=date(2024,1,31)
    with factory.begin() as db:
        db.add(m.UnitModel(id=2,code='kg'));db.flush()
        ec=m.ExpenseCategoryModel(name='SIMULACIÓN volumen');ic=m.IncomeCategoryModel(name='SIMULACIÓN volumen')
        feed=m.FeedModel(id=str(uuid4()),name='SIMULACIÓN alimento de volumen',unit_id=2)
        db.add_all([ec,ic,feed]);db.flush()
        db.add(m.FeedPriceModel(feed_id=feed.id,effective_from=date(2024,1,1),unit_cost=Decimal('8.5')))
        db.execute(insert(m.AnimalModel),[dict(id=aid,name=f'Volumen {i:04}',siniiga=f'VOLUMEN-{i:04}',sex='female' if i%2==0 else 'male',birth_date=date(2020,1,1),origin='born_in_herd',is_breeder=False) for i,aid in enumerate(ids)])
        db.execute(insert(m.AnimalGroupModel),[dict(id=gid,name=f'SIMULACIÓN lote {i}') for i,gid in enumerate(groups)])
        db.execute(insert(m.GroupAnimalModel),[dict(group_id=groups[i//100],animal_id=aid,start_date=date(2024,1,1)) for i,aid in enumerate(ids)])
        events=[];weights=[]
        for i,aid in enumerate(ids):
            for n in range(5):
                eid=str(uuid4());events.append(dict(id=eid,animal_id=aid,event_type_id=4,date=datetime(2024,1,n+1),user_id=me['id'],role_id=me['role_id']))
                weights.append(dict(event_id=eid,event_type_id=4,weight_kg=Decimal('20')+n))
        db.execute(insert(m.EventModel),events);db.execute(insert(m.EventWeightModel),weights)
        db.execute(insert(m.IncomeModel),[dict(id=str(uuid4()),income_category_id=ic.id,animal_id=aid,amount=Decimal('100'),date=day) for aid in ids])
        expenses=[];shares=[]
        for aid in ids:
            eid=str(uuid4());expenses.append(dict(id=eid,expense_category_id=ec.id,amount=Decimal('40'),date=day));shares.append(dict(id=str(uuid4()),expense_id=eid,animal_id=aid,percentage=Decimal('100')))
        for gid in groups:
            eid=str(uuid4());expenses.append(dict(id=eid,expense_category_id=ec.id,amount=Decimal('50'),date=day));shares.append(dict(id=str(uuid4()),expense_id=eid,group_id=gid,percentage=Decimal('100')))
        db.execute(insert(m.ExpenseModel),expenses);db.execute(insert(m.ExpenseAllocationModel),shares)
        db.execute(insert(m.FeedingModel),[dict(id=str(uuid4()),animal_id=aid,feed_id=feed.id,date=day,quantity=Decimal('2')) for aid in ids])
    metrics={};engine=factory.kw['bind']
    def measured(label,path,params=None):
        count=0
        def query(*args):
            nonlocal count
            count+=1
        event.listen(engine,'before_cursor_execute',query)
        start=perf_counter()
        try:r=client.get('/api/v1'+path,headers=owner,params=params)
        finally:
            elapsed=perf_counter()-start
            event.remove(engine,'before_cursor_execute',query)
        assert r.status_code==200,(label,r.text)
        metrics[label]={'milliseconds':round(elapsed*1000,2),'queries':count}
        assert elapsed<10,(label,metrics[label])
        assert count<150,(label,metrics[label])
        if label in ('animals_page','animals_next_page'):
            assert count<=12,('Animal pagination must not add SQL round trips per row',metrics[label])
        return r.json()
    first=measured('animals_page','/animals',{'limit':25})
    second=measured('animals_next_page','/animals',{'offset':25,'limit':25})
    assert first['total']==1000 and len(first['items'])==25
    assert {a['id'] for a in first['items']}.isdisjoint(a['id'] for a in second['items'])
    selected=measured('animal_search','/animals',{'q':'VOLUMEN-0999'})
    assert selected['total']==1 and selected['items'][0]['id']==ids[-1]
    result=measured('animal_profitability','/finance/profitability',{'limit':25})
    assert result['total']==1000 and len(result['items'])==25
    assert result['summary']=={'income':'100000.00','expenses':'40500.00','result':'59500.00'}
    assert result['coverage']['pending_expenses']=='0.00' and result['coverage']['pending_income']=='0.00'
    assert result['items'][0]['feeding']['known_cost']=='17.00'
    weights=measured('weight_report','/reports/weights',{'limit':25})
    assert weights['total']==5000 and len(weights['items'])==25
    history=measured('animal_timeline','/animals/'+ids[0]+'/timeline',{'limit':25})
    assert sum(i['title']=='Pesaje' for i in history['items'])==5
    distribution=measured('group_distribution','/finance/group-costs',{'kind':'group','target_id':groups[0],'view':'animals','limit':25})
    assert distribution['total']==100 and len(distribution['items'])==25
    (tmp_path/'mysql_volume_metrics.json').write_text(json.dumps(metrics,indent=2))
    print('\nMYSQL_VOLUME_METRICS '+json.dumps(metrics))
