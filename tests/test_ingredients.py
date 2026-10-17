from sqlalchemy import select
from src.core.models import AuditModel, ProductIngredientModel
from tests.conftest import login
from tests.test_treatments import product


def ingredient(client,h,name):
    r=client.post('/api/v1/health/ingredients',headers=h,json={'name':name})
    assert r.status_code==201,r.text
    return r.json()


def test_catalog_lifecycle_composition_preserved_and_audited(api):
    client,factory=api;h=login(client)
    a=ingredient(client,h,' Oxitetraciclina ');b=ingredient(client,h,'Ivermectina')
    assert a['name']=='Oxitetraciclina'
    assert client.post('/api/v1/health/ingredients',headers=h,json={'name':'oxitetraciclina'}).status_code==409
    r=product(client,h,ingredient_ids=[a['id'],b['id']]);assert r.status_code==201,r.text
    p=r.json();assert {i['id'] for i in p['ingredients']}=={a['id'],b['id']}
    assert client.delete('/api/v1/health/ingredients/'+str(a['id']),headers=h).status_code==409
    listing=client.get('/api/v1/health/ingredients?q=oxi',headers=h).json()
    assert listing['items']==[{**a,'product_count':1}]
    data={'name':p['name'],'product_type_id':1,'unit_id':1,'withdrawal_days':7,'active':True}
    # An older client omitting composition must not erase it.
    r=client.put('/api/v1/health/products/'+p['id'],headers=h,json=data)
    assert r.status_code==200,r.text
    assert len(r.json()['ingredients'])==2
    r=client.put('/api/v1/health/products/'+p['id'],headers=h,json={**data,'ingredient_ids':[a['id']]})
    assert r.status_code==200,r.text
    assert r.json()['ingredients']==[{'id':a['id'],'name':a['name']}]
    assert client.delete('/api/v1/health/ingredients/'+str(b['id']),headers=h).status_code==204
    r=client.put('/api/v1/health/ingredients/'+str(a['id']),headers=h,json={'name':'Oxitetraciclina (nombre corregido)'})
    assert r.status_code==200,r.text
    assert client.get('/api/v1/health/products',headers=h).json()['items'][0]['ingredients'][0]['name']==r.json()['name']
    with factory() as db:
        audit=db.scalars(select(AuditModel).where(AuditModel.table=='products',AuditModel.action=='UPDATE').order_by(AuditModel.date,AuditModel.id)).all()
        assert any(len(i.old_values['ingredients'])==2 and len(i.new_values['ingredients'])==1 for i in audit)
    r=client.put('/api/v1/health/products/'+p['id'],headers=h,json={**data,'ingredient_ids':[]})
    assert r.status_code==200 and r.json()['ingredients']==[]
    assert client.delete('/api/v1/health/ingredients/'+str(a['id']),headers=h).status_code==204
    with factory() as db:
        assert not db.scalar(select(ProductIngredientModel.product_id))
        assert len(db.scalars(select(AuditModel).where(AuditModel.table=='active_ingredients',AuditModel.action=='DELETE')).all())==2


def test_invalid_links_names_and_permissions_do_not_change_products(api):
    client,factory=api;h=login(client);a=ingredient(client,h,'Oxitetraciclina')
    for value in ['', '   ','x'*121]:
        assert client.post('/api/v1/health/ingredients',headers=h,json={'name':value}).status_code==422
    for ids in [[999999],[a['id'],a['id']],[0],[-1],list(range(1,102))]:
        r=product(client,h,ingredient_ids=ids);assert r.status_code==422,(ids,r.text)
    assert client.get('/api/v1/health/products',headers=h).json()['total']==0
    worker=login(client,'worker@example.com')
    for method,path,data in [('get','/ingredients',None),('post','/ingredients',{'name':'Otro'}),('put',f"/ingredients/{a['id']}",{'name':'Otro'}),('delete',f"/ingredients/{a['id']}",None)]:
        args={'json':data} if data else {}
        assert client.request(method,'/api/v1/health'+path,headers=worker,**args).status_code==403
        assert client.request(method,'/api/v1/health'+path,**args).status_code==401
    assert client.get('/api/v1/health/ingredients?limit=0',headers=h).status_code==422
    assert client.put('/api/v1/health/ingredients/999',headers=h,json={'name':'Otro'}).status_code==404
    assert client.delete('/api/v1/health/ingredients/999',headers=h).status_code==404


def test_search_is_escaped_counts_and_pagination_include_inactive_products(api):
    client,_=api;h=login(client);a=ingredient(client,h,'Ingrediente %');b=ingredient(client,h,'Otro')
    r=product(client,h,active=False,ingredient_ids=[a['id']]);assert r.status_code==201,r.text
    listing=client.get('/api/v1/health/ingredients?limit=1',headers=h).json()
    assert listing['total']==2 and len(listing['items'])==1
    assert listing['items'][0]['product_count']==1
    assert client.get('/api/v1/health/ingredients?q=%25',headers=h).json()['total']==1
    assert client.delete('/api/v1/health/ingredients/'+str(a['id']),headers=h).status_code==409
