from sqlalchemy import select
from src.core.models import AuditModel, EventMatingModel
from tests.conftest import login
from tests.test_animals import animal


def check(client,h,f,m):
    return client.get('/api/v1/breeding/kinship',headers=h,params={'animal_id':f['id'],'male_id':m['id']})


def test_direct_ancestor_shared_parents_and_partial_data(api):
    client,_=api;h=login(client)
    mother=animal(client,h,name='Madre');father=animal(client,h,name='Padre',sex='male')
    daughter=animal(client,h,name='Hija',mother_id=mother['id'],father_id=father['id'])
    son=animal(client,h,name='Hijo',sex='male',mother_id=mother['id'],father_id=father['id'])
    direct=check(client,h,daughter,father);assert direct.status_code==200,direct.text
    assert direct.json()['matches'][0]['kind']=='direct_ancestor'
    sibling=check(client,h,daughter,son).json()
    assert sibling['status']=='related' and not sibling['lineage_complete']
    assert len([m for m in sibling['matches'] if m['kind']=='shared_parent'])==2
    unknown=animal(client,h,name='Sin padres',sex='male')
    assert check(client,h,daughter,unknown).json()['status']=='insufficient_data'
    assert check(client,h,mother,mother).status_code==422
    assert check(client,h,father,son).status_code==422


def test_common_grandparent_and_historical_snapshot(api):
    client,factory=api;h=login(client)
    grandmother=animal(client,h,name='Abuela')
    parent_f=animal(client,h,name='Madre hembra',mother_id=grandmother['id'])
    parent_m=animal(client,h,name='Madre macho',mother_id=grandmother['id'])
    f=animal(client,h,name='Hembra',mother_id=parent_f['id'])
    m=animal(client,h,name='Macho',sex='male',mother_id=parent_m['id'])
    summary=check(client,h,f,m).json()
    assert summary['matches'][0]['kind']=='shared_grandparent'
    assert summary['matches'][0]['female_paths']==['mother.mother']
    r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':f['id'],'male_id':m['id'],'date':'2024-01-01'})
    assert r.status_code==201,r.text
    saved=r.json();assert saved['kinship']==summary
    with factory() as db:
        assert db.get(EventMatingModel,saved['id']).kinship_snapshot==summary
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==saved['id']))
        assert audit.new_values['kinship']==summary
    assert client.put('/api/v1/animals/'+parent_m['id'],headers=h,json={'name':'Madre macho','sex':'female'}).status_code==200
    assert check(client,h,f,m).json()['status']=='insufficient_data'
    history=client.get('/api/v1/breeding/animals/'+f['id']+'/history',headers=h).json()
    assert history['items'][0]['kinship']==summary


def test_complete_unrelated_family_and_permissions(api):
    client,_=api;h=login(client)
    def family(prefix,sex):
        grandmother1=animal(client,h,name=prefix+' abuela materna')
        grandfather1=animal(client,h,name=prefix+' abuelo materno',sex='male')
        grandmother2=animal(client,h,name=prefix+' abuela paterna')
        grandfather2=animal(client,h,name=prefix+' abuelo paterno',sex='male')
        mother=animal(client,h,name=prefix+' madre',mother_id=grandmother1['id'],father_id=grandfather1['id'])
        father=animal(client,h,name=prefix+' padre',sex='male',mother_id=grandmother2['id'],father_id=grandfather2['id'])
        return animal(client,h,name=prefix,sex=sex,mother_id=mother['id'],father_id=father['id'])
    f,m=family('Hembra','female'),family('Macho','male')
    result=check(client,h,f,m).json()
    assert result['status']=='no_relationship_found' and result['lineage_complete']
    assert result['matches']==[] and result['missing_female']==[]
    worker=login(client,'worker@example.com')
    assert check(client,worker,f,m).status_code==403
    assert client.get('/api/v1/breeding/kinship',params={'animal_id':f['id'],'male_id':m['id']}).status_code==401


def test_repeated_ancestors_keep_both_paths_and_legacy_cycles_are_bounded(api):
    from src.core.models import AnimalModel
    client,factory=api;h=login(client)
    grand=animal(client,h,name='Abuela común')
    mother=animal(client,h,name='Madre',mother_id=grand['id'])
    father=animal(client,h,name='Padre',sex='male',mother_id=grand['id'])
    f=animal(client,h,name='Hembra',mother_id=mother['id'],father_id=father['id'])
    m=animal(client,h,name='Macho',sex='male',mother_id=mother['id'])
    match=next(x for x in check(client,h,f,m).json()['matches'] if x['ancestor']['id']==grand['id'])
    assert match['female_paths']==['mother.mother','father.mother']
    with factory.begin() as db:
        db.get(AnimalModel,mother['id']).mother_id=mother['id']
    result=check(client,h,f,m).json()
    assert result['invalid_lineage'] and not result['lineage_complete']


def test_legacy_matings_do_not_invent_a_snapshot(api):
    client,factory=api;h=login(client)
    f=animal(client,h,name='Hembra');m=animal(client,h,name='Macho',sex='male')
    r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':f['id'],'male_id':m['id'],'date':'2024-01-01'})
    with factory.begin() as db:db.get(EventMatingModel,r.json()['id']).kinship_snapshot=None
    event=client.get('/api/v1/breeding/animals/'+f['id']+'/history',headers=h).json()['items'][0]
    assert event['kinship'] is None
    assert client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':f['id'],'male_id':m['id'],'date':'2024-01-02','kinship':{'status':'no_relationship_found'}}).status_code==422
