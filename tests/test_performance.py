from datetime import date, datetime
from sqlalchemy import func, select
from src.core.models import AuditModel, EventModel, RoleModel, RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal


def test_performance_births_manual_descendants_weights_and_exit_states(api):
    client,factory=api;h=login(client)
    mother=animal(client,h,name='Luna',birth_date='2020-01-01')
    father=animal(client,h,name='Trueno',sex='male',birth_date='2019-01-01')
    empty=animal(client,h,name='Sin registros',is_breeder=True)
    def birth(day,children):
        r=client.post('/api/v1/breeding/births',headers=h,json={'animal_id':mother['id'],'father_id':father['id'],'date':day,'birth_type_id':1,'offspring':children});assert r.status_code==201,r.text;return r.json()
    first=birth('2024-01-01',[{'name':'Estrella','sex':'female','birth_weight_kg':'3.00'},{'name':'Sin vida','sex':'male','alive':False,'birth_weight_kg':'2.00'}])
    second=birth('2024-06-01',[{'name':'Lucero','sex':'male','birth_weight_kg':'4.00'},{'name':'Sin peso','sex':'female'}])
    manual=animal(client,h,name='Registro manual',birth_date='2024-02-01',mother_id=mother['id'],father_id=father['id'])
    living=next(c['animal'] for c in first['offspring'] if c['alive'])
    sold=next(c['animal'] for c in second['offspring'] if c['animal']['name']=='Lucero')
    for a,state in [(living,'death'),(sold,'sale'),(mother,'sale')]:
        assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':state,'date':'2025-01-01','reason':'Salida registrada'}).status_code==201
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    r=client.get('/api/v1/breeding/performance',headers=h,params={'limit':1});assert r.status_code==200,r.text
    page=r.json();assert page['total']==2 and len(page['items'])==1 and page['summary']['offspring']==5
    data=client.get('/api/v1/breeding/performance',headers=h,params={'q':'Luna'}).json()['items'][0]
    assert data['births']==2 and data['offspring']==5 and data['offspring_per_recorded_birth']=='2.00'
    assert data['live_births']==3 and data['stillbirths']==1 and data['unknown_birth_condition']==1
    assert data['post_birth_deaths']==1 and data['in_herd']==2 and data['other_exits']==1
    assert data['weighed_offspring']==3 and data['average_birth_weight_kg']=='3.00' and data['status']=='sale'
    male=client.get('/api/v1/breeding/performance',headers=h,params={'sex':'male'}).json()['items'][0]
    assert male['animal']['id']==father['id'] and male['births']==2 and male['offspring']==5 and male['offspring_per_recorded_birth'] is None
    period=client.get('/api/v1/breeding/performance',headers=h,params={'q':'Luna','date_from':'2024-06-01','date_to':'2024-06-01'}).json()['items'][0]
    assert period['births']==1 and period['offspring']==2 and period['average_birth_weight_kg']=='4.00'
    children=client.get('/api/v1/breeding/performance/'+mother['id']+'/offspring',headers=h,params={'limit':1}).json()
    assert children['total']==5 and len(children['items'])==1 and children['parent']==data
    all_children=client.get('/api/v1/breeding/performance/'+mother['id']+'/offspring',headers=h).json()['items']
    missing=next(c for c in all_children if c['animal']['id']==manual['id']);assert missing['born_alive'] is None and missing['birth_weight_kg'] is None
    assert client.get('/api/v1/breeding/performance',headers=h,params={'q':'%'}).json()['total']==0
    active=client.get('/api/v1/breeding/performance',headers=h,params={'status':'active'}).json();assert active['total']==1 and active['items'][0]['animal']['id']==empty['id']
    assert active['items'][0]['average_birth_weight_kg'] is None and active['items'][0]['offspring_per_recorded_birth'] is None
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before
    # Replacing a birth removes its outcome/weight evidence but retains genealogy.
    with factory.begin() as db:db.get(EventModel,second['id']).replaced_event_id=first['id']
    data=client.get('/api/v1/breeding/performance',headers=h,params={'q':'Luna'}).json()['items'][0]
    assert data['births']==1 and data['offspring']==5 and data['unknown_birth_condition']==3 and data['weighed_offspring']==1


def test_performance_permissions_validation_and_missing_parent(api):
    client,factory=api;h=login(client,'worker@example.com');paths=['/api/v1/breeding/performance','/api/v1/breeding/performance/00000000-0000-4000-8000-000000000099/offspring']
    for path in paths:
        assert client.get(path).status_code==401
        assert client.get(path,headers=h).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='breeding:read'))
    assert client.get(paths[0],headers=h).status_code==200
    assert client.get(paths[1],headers=h).status_code==404
    assert client.get('/api/v1/animals',headers=h).status_code==403
    for params in ({'date_from':'2024-02-01','date_to':'2024-01-01'},{'limit':101},{'sex':'bad'},{'status':'bad'},{'q':'x'*101}):assert client.get(paths[0],headers=h,params=params).status_code==422


def test_performance_observed_weanings_cohort_and_historical_age(api):
    from tests.test_weanings import wean
    from tests.test_weights import post as weigh
    client,factory=api;h=login(client)
    mother=animal(client,h,name='Luna',birth_date='2020-01-01')
    father=animal(client,h,name='Trueno',sex='male',birth_date='2020-01-01')
    a=animal(client,h,name='Estrella',birth_date='2024-01-01',mother_id=mother['id'],father_id=father['id'])
    b=animal(client,h,name='Lucero',birth_date='2024-01-02',mother_id=mother['id'],father_id=father['id'])
    missing=animal(client,h,name='Sin destete',birth_date='2024-01-03',mother_id=mother['id'],father_id=father['id'])
    unknown=animal(client,h,name='Sin nacimiento',mother_id=mother['id'],father_id=father['id'])
    assert weigh(client,h,a['id'],'2024-03-01','18.50').status_code==201
    marker=wean(client,h,a);assert marker.status_code==201
    assert wean(client,h,b,weight_kg='21.51').status_code==201
    assert wean(client,h,unknown,weight_kg='20').status_code==201
    assert weigh(client,h,missing['id'],'2024-03-01','99').status_code==201
    assert weigh(client,h,a['id'],'2024-04-01','40').status_code==201
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-04-02','exit_type':'sale','reason':'Venta'}).status_code==201
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Estrella','sex':'female','birth_date':'2024-01-02','mother_id':mother['id'],'father_id':father['id']}).status_code==200
    for sex,parent in [('female',mother),('male',father)]:
        result=client.get('/api/v1/breeding/performance',headers=h,params={'sex':sex}).json()
        metric=next(r for r in result['items'] if r['animal']['id']==parent['id'])
        assert metric['offspring']==4 and metric['weaned_offspring']==3 and metric['average_weaning_weight_kg']=='20.00'
        assert result['summary']['weaned_offspring']==3
        # The period selects births, not weaning dates; the March observations belong to the January cohort.
        f={'date_from':'2024-01-01','date_to':'2024-01-31'}
        metric=client.get('/api/v1/breeding/performance',headers=h,params={'sex':sex,**f}).json()['items'][0]
        assert metric['weaned_offspring']==2 and metric['average_weaning_weight_kg']=='20.01'
        detail=client.get('/api/v1/breeding/performance/'+parent['id']+'/offspring',headers=h,params=f).json()
        assert detail['parent']==metric
        by_id={c['animal']['id']:c for c in detail['items']}
        assert by_id[a['id']]['status']=='sale' and by_id[a['id']]['weaning']=={'date':'2024-03-01','weight_kg':'18.50','age_days':60}
        assert by_id[missing['id']]['weaning'] is None
        outside=client.get('/api/v1/breeding/performance',headers=h,params={'sex':sex,'date_from':'2024-03-01'}).json()['items'][0]
        assert outside['weaned_offspring']==0 and outside['average_weaning_weight_kg'] is None
    full=client.get('/api/v1/breeding/performance/'+mother['id']+'/offspring',headers=h).json()
    assert next(c for c in full['items'] if c['animal']['id']==unknown['id'])['weaning']['age_days'] is None
    # A replaced weighing is not counted as an effective weaning observation.
    with factory.begin() as db:
        replacement=db.scalar(select(EventModel).where(EventModel.animal_id==a['id'],EventModel.date==datetime(2024,4,1)))
        replacement.replaced_event_id=marker.json()['id']
    metric=client.get('/api/v1/breeding/performance',headers=h).json()['items'][0]
    assert metric['weaned_offspring']==2 and metric['average_weaning_weight_kg']=='20.76'
