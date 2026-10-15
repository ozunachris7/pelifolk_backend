from uuid import uuid4
from sqlalchemy import select
from src.core.models import AnimalModel, EventModel
from tests.conftest import login
from tests.test_animals import animal


def candidates(client,h,root,**params):
    return client.get('/api/v1/animals',headers=h,params={'parent_of':root['id'],**params})


def test_excludes_descendants_for_both_parents_at_all_generations(api):
    client,_=api;h=login(client)
    luna=animal(client,h,name='Luna')
    aurora=animal(client,h,name='Aurora',mother_id=luna['id'])
    son=animal(client,h,name='Hijo',sex='male',mother_id=luna['id'])
    granddaughter=animal(client,h,name='Nieta',father_id=son['id'])
    grandson=animal(client,h,name='Nieto',sex='male',mother_id=aurora['id'])
    great=animal(client,h,name='Bisnieta',father_id=grandson['id'])
    other=animal(client,h,name='Otra hembra')
    father=animal(client,h,name='Otro macho',sex='male')
    excluded={luna['id'],aurora['id'],son['id'],granddaughter['id'],grandson['id'],great['id']}
    for sex,expected in [('female',other['id']),('male',father['id'])]:
        page=candidates(client,h,luna,sex=sex,limit=1).json()
        assert page['total']==1 and [a['id'] for a in page['items']]==[expected]
        assert set(page['excluded_parent_ids'])==excluded
    assert candidates(client,h,luna,sex='female',q='Aurora').json()['total']==0
    assert aurora['id'] in [a['id'] for a in candidates(client,h,other,sex='female').json()['items']]
    # Preserve generic exclude_id semantics and the existing write protection.
    assert aurora['id'] in [a['id'] for a in client.get('/api/v1/animals',headers=h,params={'exclude_id':luna['id']}).json()['items']]
    assert client.put('/api/v1/animals/'+luna['id'],headers=h,json={'name':'Luna','sex':'female','mother_id':aurora['id']}).status_code==422


def test_father_descendants_missing_parent_dates_and_legacy_cycles(api):
    client,factory=api;h=login(client)
    father=animal(client,h,name='Padre',sex='male')
    child=animal(client,h,name='Cría',father_id=father['id'])
    grand=animal(client,h,name='Nieta',mother_id=child['id'])
    with factory.begin() as db:
        db.get(AnimalModel,father['id']).mother_id=grand['id'] # legacy cycle
    page=candidates(client,h,father).json()
    assert page['total']==0
    assert set(page['excluded_parent_ids'])=={father['id'],child['id'],grand['id']}


def test_permissions_unknown_root_and_regular_lists(api):
    client,_=api;h=login(client);a=animal(client,h);worker=login(client,'worker@example.com')
    assert candidates(client,worker,a).status_code==403
    assert client.get('/api/v1/animals',params={'parent_of':a['id']}).status_code==401
    assert client.get('/api/v1/animals',headers=h,params={'parent_of':str(uuid4())}).status_code==404
    assert client.get('/api/v1/animals',headers=h,params={'parent_of':'invalid'}).status_code==422
    page=client.get('/api/v1/animals',headers=h).json()
    assert page['total']==1 and page['excluded_parent_ids']==[]


def test_reproductive_partners_are_not_offered_as_new_parents(api):
    client,_=api;h=login(client)
    luna=animal(client,h,name='Luna');trueno=animal(client,h,name='Trueno',sex='male')
    other=animal(client,h,name='Otra hembra')
    r=client.post('/api/v1/breeding/matings',headers=h,json={
        'animal_id':luna['id'],'male_id':trueno['id'],'date':'2024-01-01'})
    assert r.status_code==201,r.text
    assert trueno['id'] not in [a['id'] for a in candidates(client,h,luna,sex='male').json()['items']]
    assert luna['id'] not in [a['id'] for a in candidates(client,h,trueno,sex='female').json()['items']]
    assert trueno['id'] in [a['id'] for a in candidates(client,h,other,sex='male').json()['items']]


def test_shared_offspring_identify_partner_without_a_mating(api):
    client,_=api;h=login(client)
    luna=animal(client,h,name='Luna');trueno=animal(client,h,name='Trueno',sex='male')
    aurora=animal(client,h,name='Aurora',mother_id=luna['id'],father_id=trueno['id'])
    female_page=candidates(client,h,trueno,sex='female').json()
    assert luna['id'] in female_page['excluded_parent_ids']
    assert aurora['id'] in female_page['excluded_parent_ids']
    assert female_page['total']==0
    assert candidates(client,h,luna,sex='male').json()['total']==0


def test_preexisting_parent_is_preserved_if_a_related_mating_was_recorded(api):
    client,_=api;h=login(client)
    father=animal(client,h,name='Padre',sex='male')
    daughter=animal(client,h,name='Hija',father_id=father['id'])
    r=client.post('/api/v1/breeding/matings',headers=h,json={
        'animal_id':daughter['id'],'male_id':father['id'],'date':'2024-01-01'})
    assert r.status_code==201,r.text
    page=candidates(client,h,daughter,sex='male').json()
    assert father['id'] in [a['id'] for a in page['items']]
    assert father['id'] not in page['excluded_parent_ids']
    # The daughter is still excluded from the father's parents as his descendant.
    assert candidates(client,h,father,sex='female').json()['total']==0
