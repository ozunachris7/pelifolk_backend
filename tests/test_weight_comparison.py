from datetime import datetime
from sqlalchemy import select
from src.core.models import EventModel, ExitModel, UserModel
from tests.conftest import login
from tests.test_animals import animal


def test_comparison_options_include_exited_only_when_requested(api):
    client,factory=api;headers=login(client)
    active=animal(client,headers,name='Demo active',birth_date='2020-01-01')
    exited=animal(client,headers,name='Demo exited',siniiga='EXITED-001',birth_date='2020-01-01')
    assert client.post('/api/v1/weights',headers=headers,json={'animal_id':exited['id'],'date':'2024-01-01','weight_kg':'30.00'}).status_code==201
    with factory.begin() as db:
        owner=db.scalar(select(UserModel).where(UserModel.email=='owner@example.com'))
        event=EventModel(animal_id=exited['id'],event_type_id=8,date=datetime(2024,2,1),user_id=owner.id,role_id=owner.role_id)
        db.add(event);db.flush();db.add(ExitModel(event_id=event.id,exit_type='sale'))
    url='/api/v1/weights/animal-options'
    assert [r['id'] for r in client.get(url,headers=headers).json()]==[active['id']]
    data=client.get(url,headers=headers,params={'include_exited':True,'q':'EXITED-001'}).json()
    assert [r['id'] for r in data]==[exited['id']]
    history=client.get(f"/api/v1/weights/animals/{exited['id']}/history",headers=headers).json()
    assert len(history['items'])==1 and history['items'][0]['weight_kg']=='30.00'
    assert client.get(url,params={'include_exited':True}).status_code==401
    assert client.get(url,headers=login(client,'worker@example.com'),params={'include_exited':True}).status_code==403
