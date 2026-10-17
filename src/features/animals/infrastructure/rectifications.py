"""Append-only clarifications and validated event replacements; no history deletion."""
import hashlib
import json
from datetime import timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select, union_all, or_
from sqlalchemy.orm import Session
from src.core import models as m
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.health.domain.dto import ObservationInput, DiagnosisInput
from src.features.health.infrastructure.repository import SQLHealthRepository
from src.features.weights.domain.dto import WeightInput
from src.features.weights.infrastructure.repository import SQLWeightRepository
from .timeline import Timeline, sources

router = APIRouter(prefix='/animals', tags=['Historical rectifications'], dependencies=[Depends(require_permission('animals:read'))])
EVENT_ACTION = {1:'health:observations:create',2:'health:diagnoses:create',3:'health:treatments:create',4:'weights:write',5:'breeding:write',6:'breeding:write',7:'breeding:write',8:'exits:write',9:'locations:write'}
HEALTH_ACTION = {'dose':'doses:create','followup':'followups:create','case_open':'cases:write','case_change':'cases:write','incident':'incidents:write','incident_followup':'incidents:write','reaction':'reactions:write','reaction_closure':'reactions:write'}


class RectificationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entry_id: str = Field(min_length=1,max_length=200)
    expected_version: int = Field(ge=0)
    snapshot_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    mode: Literal['clarification','weight','observation','diagnosis']
    reason: str = Field(min_length=10,max_length=2000)
    clarification: str | None = Field(default=None,min_length=10,max_length=5000)
    weight: WeightInput | None = None
    observation: ObservationInput | None = None
    diagnosis: DiagnosisInput | None = None

    @field_validator('reason','clarification',mode='before')
    @classmethod
    def trim(cls,v):
        return v.strip() if isinstance(v,str) else v

    @model_validator(mode='after')
    def matching_payload(self):
        provided = [name for name in ('clarification','weight','observation','diagnosis') if getattr(self,name) is not None]
        if provided != [self.mode]:
            raise ValueError('Provide only the payload matching the rectification mode')
        return self


def fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def ancestors(db, ref):
    ids = {ref}
    event = db.get(m.EventModel,ref)
    while event and event.replaced_event_id and event.replaced_event_id not in ids:
        ids.add(event.replaced_event_id)
        event = db.get(m.EventModel,event.replaced_event_id)
    return ids


def resolve(db, animal_id, key, permissions):
    try:
        kind,ref,day = key.split(':',2)
    except ValueError:
        raise ApplicationError('History entry not found',404)
    combined = union_all(*sources(animal_id,permissions)).subquery()
    row = db.execute(select(combined).where(combined.c.kind==kind,combined.c.reference==ref,combined.c.date==day)).first()
    if not row:
        raise ApplicationError('History entry is unavailable or has changed; reload history',409)
    return row,Timeline(db,animal_id,permissions).response(row)


def records(db,animal_id,key,ref,kind,module):
    condition = m.HistoryRectificationModel.entry_key==key
    if kind not in ('group_start','group_end'):
        condition=or_(condition,(m.HistoryRectificationModel.source_ref==ref) & m.HistoryRectificationModel.entry_key.startswith(kind+':',autoescape=True))
    if kind == 'event':
        ids=ancestors(db,ref)
        condition=or_(condition,m.HistoryRectificationModel.source_ref.in_(ids),m.HistoryRectificationModel.replacement_event_id.in_(ids))
    return list(db.scalars(select(m.HistoryRectificationModel).where(m.HistoryRectificationModel.animal_id==animal_id,
        m.HistoryRectificationModel.module==module,condition).order_by(m.HistoryRectificationModel.created_at,m.HistoryRectificationModel.id)))


def response(row):
    return dict(id=row.id,version=row.version,mode=row.mode,reason=row.reason,clarification=row.clarification,
        original=row.source_snapshot,corrected=row.corrected_snapshot,replacement_event_id=row.replacement_event_id,
        recorded_by=row.recorded_by,role_name=row.role_name,created_at=row.created_at.replace(tzinfo=timezone.utc).isoformat())


def context(db,animal_id,key,actor):
    row,snapshot=resolve(db,animal_id,key,actor.role.permissions)
    ref,day,kind,module=row
    event=db.get(m.EventModel,ref) if kind=='event' else None
    if event and event.animal_id != animal_id:
        # Matings and births can appear on the other parent's timeline; correct them from their primary animal.
        action=None
    else:
        action=EVENT_ACTION.get(event.event_type_id) if event else ('health:'+HEALTH_ACTION[kind] if kind in HEALTH_ACTION else module+':write')
    if event and event.event_type_id==3:
        treatments=list(db.scalars(select(m.EventTreatmentModel).where(m.EventTreatmentModel.event_id==event.id)))
        if treatments and all(t.program_id for t in treatments): action='health:program_applications:create'
    allowed='history:rectify' in actor.role.permissions and action in actor.role.permissions
    entries=records(db,animal_id,key,ref,kind,module)
    version=max((r.version for r in entries if r.entry_key==key),default=0)
    mode=None;initial=None;blocked=None
    if event and event.event_type_id==4:
        weight=db.get(m.EventWeightModel,ref)
        if db.get(m.EventWeaningModel,ref):blocked='El peso pertenece a un destete. Puedes agregar una aclaración sin modificar ese comprobante.'
        elif db.scalar(select(m.IncomeModel.id).where(m.IncomeModel.weight_event_id==ref).limit(1)):blocked='Este pesaje respalda una venta. Puedes agregar una aclaración sin modificar el comprobante económico.'
        else:mode='weight';initial=dict(animal_id=animal_id,date=event.date.date().isoformat(),weight_kg=str(weight.weight_kg),notes=event.reason)
    elif event and event.event_type_id==1:
        if db.get(m.CaseObservationModel,ref):blocked='La observación es el origen de un caso. Puedes aclararla conservando el vínculo original.'
        else:mode='observation';initial=dict(animal_id=animal_id,date=event.date.date().isoformat(),observation=db.get(m.EventObservationModel,ref).observation)
    elif event and event.event_type_id==2:
        d=db.get(m.EventDiagnosisModel,ref)
        if db.get(m.HealthCaseModel,d.health_case_id).status=='closed':blocked='El caso está cerrado. Puedes aclararlo; para sustituir el diagnóstico primero debes reabrir el caso.'
        else:mode='diagnosis';initial=dict(date=event.date.date().isoformat(),diagnosis=d.diagnosis,severity=d.severity)
    if event and event.animal_id != animal_id:blocked='Este evento pertenece a otro animal; rectifícalo desde su ficha principal.'
    if not mode and not blocked:blocked='Este registro admite aclaraciones. La aclaración no cambia sus importes, fechas ni efectos operativos.'
    return dict(source=snapshot,snapshot_token=fingerprint(snapshot),version=version,can_rectify=allowed,
        replacement_mode=mode if allowed else None,initial=initial if allowed else None,explanation=blocked,
        entries=[response(r) for r in entries]),event


@router.get('/{animal_id}/rectifications')
def listing(animal_id:UUID,entry_id:str=Query(min_length=1,max_length=200),actor=Depends(require_permission('animals:read')),
            db:Session=Depends(get_db,scope='function')):
    if not db.get(m.AnimalModel,str(animal_id)):raise ApplicationError('Animal not found',404)
    return context(db,str(animal_id),entry_id,actor)[0]


@router.post('/{animal_id}/rectifications',status_code=201)
def create(animal_id:UUID,data:RectificationInput,actor=Depends(require_permission('history:rectify')),
           db:Session=Depends(get_db,scope='function')):
    aid=str(animal_id)
    # Serialize rectifications with other writes to this animal. A unique version also protects SQLite/tests.
    if not db.scalar(select(m.AnimalModel).where(m.AnimalModel.id==aid).with_for_update()):raise ApplicationError('Animal not found',404)
    c,event=context(db,aid,data.entry_id,actor)
    if not c['can_rectify']:raise ApplicationError('Insufficient permissions',403)
    if c['version']!=data.expected_version or c['snapshot_token']!=data.snapshot_token:
        raise ApplicationError('History changed; reload the rectification before saving',409)
    replacement=None
    if data.mode!='clarification':
        if c['replacement_mode']!=data.mode:raise ApplicationError('This entry only allows a historical clarification',409)
        if db.scalar(select(m.EventModel.id).where(m.EventModel.replaced_event_id==event.id).limit(1)):
            raise ApplicationError('History changed; reload the rectification before saving',409)
        initial=c['initial']
        if data.mode=='weight':
            from decimal import Decimal
            unchanged=(data.weight.date.isoformat()==initial['date'] and data.weight.weight_kg==Decimal(initial['weight_kg']) and data.weight.notes==initial['notes'])
        elif data.mode=='observation':
            unchanged=(data.observation.date.isoformat()==initial['date'] and data.observation.observation==initial['observation'])
        else:
            unchanged=(data.diagnosis.model_dump(mode='json')==initial)
        if unchanged:raise ApplicationError('Corrected data must differ from the original',422)
        if data.mode=='weight':
            if str(data.weight.animal_id)!=aid:raise ApplicationError('Rectification must preserve the original animal',422)
            replacement=SQLWeightRepository(db).create(data.weight,actor,replacing_event_id=event.id)
        elif data.mode=='observation':
            if str(data.observation.animal_id)!=aid:raise ApplicationError('Rectification must preserve the original animal',422)
            replacement=SQLHealthRepository(db).create_observation(data.observation,actor)
        else:
            d=db.get(m.EventDiagnosisModel,event.id)
            replacement=SQLHealthRepository(db).create_diagnosis(d.health_case_id,data.diagnosis,actor)
        new_event=db.get(m.EventModel,replacement['id'])
        new_event.replaced_event_id=event.id
        db.flush()
    ref=c['source']['id'].split(':',2)[1]
    row=m.HistoryRectificationModel(animal_id=aid,entry_key=data.entry_id,source_ref=ref,module=c['source']['module'],
        version=c['version']+1,mode=data.mode,reason=data.reason,clarification=data.clarification,
        source_snapshot=c['source'],corrected_snapshot=getattr(data,data.mode).model_dump(mode='json') if replacement else None,
        replacement_event_id=replacement['id'] if replacement else None,user_id=actor.id,role_id=actor.role.id,
        recorded_by=' '.join(filter(None,[actor.name,actor.middle_name,actor.paternal_lastname,actor.maternal_lastname])),role_name=actor.role.name)
    db.add(row);db.flush()
    db.add(m.AuditModel(user_id=actor.id,table='history_rectifications',record_id=row.id,action='INSERT',
        new_values=dict(animal_id=aid,module=row.module,entry_key=row.entry_key,mode=row.mode,reason=row.reason,
                        clarification=row.clarification,original=row.source_snapshot,corrected=row.corrected_snapshot,
                        replacement_event_id=row.replacement_event_id,role_id=actor.role.id)))
    db.flush()
    return response(row)
