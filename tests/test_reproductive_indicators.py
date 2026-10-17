from datetime import date,timedelta
from sqlalchemy import select,func
from src.core.models import EventModel,AuditModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
URL='/api/v1/breeding/indicators'

def pair(client,h):
    return animal(client,h,name='Luna',siniiga='IND-M',birth_date='2020-01-01'),animal(client,h,name='Trueno',sex='male',birth_date='2020-01-01')
def birth(client,h,m,f,day,children=None):
    r=client.post('/api/v1/breeding/births',headers=h,json={'animal_id':m['id'],'father_id':f['id'],'date':day,'birth_type_id':1,'offspring':children or [{'name':'Cría','sex':'female'}]});assert r.status_code==201,r.text;return r.json()
def mating(client,h,m,f,day):
    r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':m['id'],'male_id':f['id'],'date':day});assert r.status_code==201,r.text;return r.json()
def diagnosis(client,h,m,mating,day,result):
    r=client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':m['id'],'mating_event_id':mating['id'] if mating else None,'date':day,'result':result});assert r.status_code==201,r.text;return r.json()
def listing(client,h,**filters):
    r=client.get(URL,headers=h,params={'as_of':'2024-12-31',**filters});assert r.status_code==200,r.text;return r.json()


def test_birth_intervals_anchor_later_birth_and_keep_predecessor_outside_period(api):
    client,factory=api;h=login(client);m,f=pair(client,h)
    a=birth(client,h,m,f,'2024-01-01');b=birth(client,h,m,f,'2024-06-01');c=birth(client,h,m,f,'2024-12-01')
    p=listing(client,h,date_from='2024-06-01',date_to='2024-06-30');r=p['items'][0]
    assert r['births']==1 and r['birth_intervals']['count']==1 and r['birth_intervals']['average_days']=='152.00'
    detail=client.get(URL+'/'+m['id']+'/details',headers=h,params={'as_of':'2024-12-31','date_from':'2024-06-01','date_to':'2024-06-30'}).json()
    assert detail['items'][0]['previous_birth_id']==a['id'] and detail['items'][0]['predecessor_outside_period']
    assert listing(client,h,as_of='2024-02-01')['items'][0]['birth_intervals']['average_days'] is None
    with factory.begin() as db:db.get(EventModel,c['id']).replaced_event_id=b['id']
    r=listing(client,h)['items'][0];assert r['birth_intervals']['count']==1 and r['birth_intervals']['average_days']=='335.00'


def test_linked_diagnoses_are_cohort_based_latest_asof_with_explicit_unknowns(api):
    client,_=api;h=login(client);m,f=pair(client,h)
    a=mating(client,h,m,f,'2024-01-01');b=mating(client,h,m,f,'2024-01-02');c=mating(client,h,m,f,'2024-01-03')
    d=mating(client,h,m,f,'2024-01-04')
    diagnosis(client,h,m,a,'2024-02-01','pregnant');diagnosis(client,h,m,a,'2024-03-01','uncertain')
    diagnosis(client,h,m,b,'2024-02-02','not_pregnant');diagnosis(client,h,m,c,'2024-02-03','pregnant');diagnosis(client,h,m,None,'2024-01-20','pregnant')
    r=listing(client,h,date_from='2024-01-01',date_to='2024-01-31')['items'][0]['pregnancy']
    assert r['matings']==4 and r['pregnant']==1 and r['not_pregnant']==1 and r['uncertain']==1 and r['no_diagnosis']==1
    assert r['diagnosed']==2 and r['percentage']=='50.00' and r['unlinked_diagnoses']==1
    assert r['first_positive_delay']['count']==2 and r['first_positive_delay']['average_days']=='31.00'
    earlier=listing(client,h,as_of='2024-02-10')['items'][0]['pregnancy'];assert earlier['pregnant']==2 and earlier['percentage']=='66.67'
    first=listing(client,h,as_of='2024-01-31')['items'][0]['pregnancy'];assert first['diagnosed']==0 and first['percentage'] is None
    details=client.get(URL+'/'+m['id']+'/details?section=matings&as_of=2024-12-31&limit=1',headers=h).json();assert details['total']==4


def test_fixed_age_followup_separates_early_sales_deaths_immature_and_unknown(api):
    client,_=api;h=login(client);m,f=pair(client,h)
    b=birth(client,h,m,f,'2024-01-01',[{'name':name,'sex':'female','alive':name!='Sin vida'} for name in ['Sin muerte','Muerte','Vendida','Muerte después','Sin vida']])
    children={c['animal']['name']:c['animal'] for c in b['offspring']}
    for name,kind,day in [('Muerte','death','2024-01-20'),('Vendida','sale','2024-01-20'),('Muerte después','death','2024-04-01')]:
        assert client.post('/api/v1/exits',headers=h,json={'animal_id':children[name]['id'],'date':day,'exit_type':kind,'reason':'Salida registrada'}).status_code==201
    manual=animal(client,h,name='Sin condición al nacer',birth_date='2024-01-02',mother_id=m['id'])
    animal(client,h,name='Sin fecha',mother_id=m['id'])
    birth(client,h,m,f,'2024-12-20')
    r=listing(client,h,age_days=60)['items'][0]['followup']
    assert r['total']==8 and r['observable']==3 and r['without_recorded_death']==2 and r['deaths']==1
    assert r['percentage']=='66.67' and r['unobservable']==1 and r['too_young']==1 and r['stillbirths']==1
    assert r['unknown_birth_condition']==1 and r['missing_birth_date']==1
    # A later death cannot change the outcome at 60 days; an early sale is not assumed alive or dead.
    detail=client.get(URL+'/'+m['id']+'/details?section=offspring&as_of=2024-12-31&age_days=60',headers=h).json()['items']
    by_name={d['animal']['name']:d for d in detail}
    assert by_name['Muerte después']['state']=='without_recorded_death' and by_name['Muerte después']['exit_date'] is None
    assert by_name['Vendida']['state']=='unobservable' and by_name['Sin condición al nacer']['born_alive'] is None
    early=listing(client,h,as_of='2024-01-31')['items'][0]['followup'];assert early['observable']==0 and early['percentage'] is None


def test_summary_is_weighted_across_all_pages_and_reports_are_read_only(api):
    client,factory=api;h=login(client);m,f=pair(client,h);other=animal(client,h,name='Otra',siniiga='IND-O',birth_date='2020-01-01')
    for mother,day,result in [(m,'2024-01-01','pregnant'),(other,'2024-01-01','not_pregnant'),(other,'2024-01-02','pregnant')]:
        a=mating(client,h,mother,f,day);diagnosis(client,h,mother,a,'2024-02-10',result)
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    p=listing(client,h,limit=1);assert p['total']==2 and len(p['items'])==1
    assert p['summary']['pregnancy']['percentage']=='66.67' and p['summary']['pregnancy']['diagnosed']==3
    assert listing(client,h,q='%')['total']==0
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before


def test_access_validation_and_empty_denominators(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');m,f=pair(client,h)
    assert client.get(URL).status_code==401 and client.get(URL,headers=worker).status_code==403
    for params in ({'age_days':0},{'age_days':731},{'date_from':'2024-02-01','date_to':'2024-01-01'},
                   {'as_of':(date.today()+timedelta(days=1)).isoformat()},{'as_of':'2024-01-01','date_to':'2024-02-01'},{'limit':101}):
        assert client.get(URL,headers=h,params=params).status_code==422
    assert client.get(URL+'/'+f['id']+'/details',headers=h).status_code==422
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='breeding:read'))
    assert client.get(URL,headers=worker).status_code==200
    empty=listing(client,h)['summary'];assert empty['pregnancy']['percentage'] is None and empty['followup']['percentage'] is None


def test_replaced_diagnosis_is_excluded_and_mother_filter_keeps_its_own_base(api):
    client,factory=api;h=login(client);m,f=pair(client,h);a=mating(client,h,m,f,'2024-01-01')
    positive=diagnosis(client,h,m,a,'2024-02-01','pregnant');negative=diagnosis(client,h,m,a,'2024-03-01','not_pregnant')
    with factory.begin() as db:db.get(EventModel,negative['id']).replaced_event_id=positive['id']
    r=listing(client,h,animal_id=m['id']);assert r['total']==1
    assert r['summary']['pregnancy']['percentage']=='0.00' and r['summary']['pregnancy']['diagnosed']==1
    assert r['summary']['pregnancy']['first_positive_delay']['count']==0
    # The cut filters the current effective history, not a reconstruction of former database versions.
    earlier=listing(client,h,as_of='2024-02-10')['items'][0]['pregnancy'];assert earlier['diagnosed']==0 and earlier['percentage'] is None
