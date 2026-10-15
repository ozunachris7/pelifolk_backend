"""Permission-scoped, read-only timeline of recorded animal activity."""
from datetime import date, datetime, timezone
from typing import Literal, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, aliased
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core import models as m
from src.features.auth.infrastructure.dependencies import require_permission

router = APIRouter(prefix='/animals', tags=['Animal history'])
Module = Literal['animals', 'health', 'weights', 'breeding', 'locations', 'groups', 'feeding', 'finance', 'exits']
EVENT_MODULES = {1:'health', 2:'health', 3:'health', 4:'weights', 5:'breeding', 6:'breeding', 7:'breeding', 8:'exits', 9:'locations'}


def projection(model, reference, day, kind, module):
    return select(cast(reference, String).label('reference'), cast(day, String).label('date'),
                  literal(kind).label('kind'), literal(module).label('module')).select_from(model)


def sources(animal_id, permissions):
    result = [projection(m.AnimalModel, m.AnimalModel.id, m.AnimalModel.birth_date, 'birth_date', 'animals').where(
        m.AnimalModel.id == animal_id, m.AnimalModel.birth_date.is_not(None))]
    result.append(projection(m.AnimalModel, m.AnimalModel.id, m.AnimalModel.created_at, 'registration', 'animals').where(m.AnimalModel.id == animal_id))
    result.append(projection(m.AnimalDecisionModel, m.AnimalDecisionModel.id, m.AnimalDecisionModel.date, 'decision', 'animals').where(m.AnimalDecisionModel.animal_id == animal_id))
    replacement = aliased(m.EventModel)
    for number, module in EVENT_MODULES.items():
        if module+':read' not in permissions:
            continue
        involved = m.EventModel.animal_id == animal_id
        if number == 5:
            involved = or_(involved, exists(select(m.EventMatingModel.event_id).where(
                m.EventMatingModel.event_id == m.EventModel.id, m.EventMatingModel.male_id == animal_id)))
        if number == 7:
            involved = or_(involved, exists(select(m.BirthOffspringModel.animal_id).join(
                m.AnimalModel, m.AnimalModel.id == m.BirthOffspringModel.animal_id).where(
                    m.BirthOffspringModel.event_id == m.EventModel.id, m.AnimalModel.father_id == animal_id)))
        result.append(projection(m.EventModel, m.EventModel.id, m.EventModel.date, 'event', module).where(
            involved, m.EventModel.event_type_id == number,
            ~exists(select(replacement.id).where(replacement.replaced_event_id == m.EventModel.id))))
    if 'health:read' in permissions:
        cases = select(m.HealthCaseModel.id).where(m.HealthCaseModel.animal_id == animal_id)
        result.append(projection(m.HealthCaseModel, m.HealthCaseModel.id, m.HealthCaseModel.start_date, 'case_open', 'health').where(m.HealthCaseModel.animal_id == animal_id))
        result.append(projection(m.CaseFollowupModel, m.CaseFollowupModel.id, m.CaseFollowupModel.date, 'followup', 'health').where(m.CaseFollowupModel.health_case_id.in_(cases)))
        result.append(projection(m.AuditModel, m.AuditModel.id, m.AuditModel.date, 'case_change', 'health').where(
            m.AuditModel.table == 'health_cases', m.AuditModel.action == 'UPDATE', m.AuditModel.record_id.in_(cases)))
    if 'groups:read' in permissions:
        for column, kind in [(m.GroupAnimalModel.start_date, 'group_start'), (m.GroupAnimalModel.end_date, 'group_end')]:
            result.append(projection(m.GroupAnimalModel, m.GroupAnimalModel.group_id, column, kind, 'groups').where(
                m.GroupAnimalModel.animal_id == animal_id, column.is_not(None)))
    if 'feeding:read' in permissions:
        membership = exists(select(m.GroupAnimalModel.animal_id).where(
            m.GroupAnimalModel.animal_id == animal_id, m.GroupAnimalModel.group_id == m.FeedingModel.group_id,
            m.GroupAnimalModel.start_date <= m.FeedingModel.date,
            or_(m.GroupAnimalModel.end_date.is_(None), m.GroupAnimalModel.end_date >= m.FeedingModel.date)))
        result.append(projection(m.FeedingModel, m.FeedingModel.id, m.FeedingModel.date, 'feeding', 'feeding').where(
            or_(m.FeedingModel.animal_id == animal_id, membership)))
    if 'finance:read' in permissions:
        cases = select(m.HealthCaseModel.id).where(m.HealthCaseModel.animal_id == animal_id)
        attributed = exists(select(m.ExpenseAllocationModel.id).where(m.ExpenseAllocationModel.expense_id == m.ExpenseModel.id,
            or_(m.ExpenseAllocationModel.animal_id == animal_id, m.ExpenseAllocationModel.health_case_id.in_(cases))))
        result.append(projection(m.ExpenseModel, m.ExpenseModel.id, m.ExpenseModel.date, 'expense', 'finance').where(attributed))
        exits = select(m.EventModel.id).where(m.EventModel.animal_id == animal_id)
        result.append(projection(m.IncomeModel, m.IncomeModel.id, m.IncomeModel.date, 'income', 'finance').where(m.IncomeModel.exit_event_id.in_(exits)))
    return result


class Timeline:
    def __init__(self, db, animal_id, permissions):
        self.db, self.animal_id, self.permissions = db, animal_id, permissions
        self.cache = {}

    def get(self, model, key):
        cache_key = (model, key)
        if cache_key not in self.cache:
            self.cache[cache_key] = self.db.get(model, key) if key else None
        return self.cache[cache_key]

    def name(self, model, key):
        obj = self.get(model, key)
        return (getattr(obj, 'name', None) or getattr(obj, 'siniiga', None) or key) if obj else 'Sin registro'

    def author(self, key):
        user = self.get(m.UserModel, key)
        return ' '.join(filter(None, [user.name, user.middle_name, user.paternal_lastname, user.maternal_lastname])) if user else None

    def initial_author(self, table, key):
        author = self.db.scalar(select(m.AuditModel.user_id).where(m.AuditModel.table == table,
            m.AuditModel.record_id == key, m.AuditModel.action == 'INSERT').order_by(m.AuditModel.date, m.AuditModel.id).limit(1))
        return self.author(author)

    def response(self, row):
        ref, day, kind, module = row
        item = dict(id=f'{kind}:{ref}:{day}', date=day[:10], kind=kind, module=module,
                    title='', details=[], notes=None, recorded_by=None)
        def detail(label, value):
            if value is not None:
                item['details'].append(dict(label=label, value=str(value)))
        if kind == 'birth_date':
            item['title'] = 'Fecha de nacimiento registrada'
            # Identity date is current; birth evidence is included only with reproductive access.
            if 'breeding:read' in self.permissions:
                link = self.get(m.BirthOffspringModel, ref)
                if link:
                    event = self.get(m.EventModel, link.event_id)
                    replaced = self.db.scalar(select(m.EventModel.id).where(m.EventModel.replaced_event_id == event.id).limit(1))
                    if not replaced:
                        detail('Peso al nacer (kg)', link.birth_weight_kg)
                        detail('Condición al nacer', 'Viva' if link.alive else 'Sin vida')
                        item['recorded_by'] = self.author(event.user_id)
        elif kind == 'registration':
            item.update(title='Alta en el sistema', recorded_by=self.initial_author('animals', ref))
            detail('Fecha de registro', 'UTC')
        elif kind == 'decision':
            d = self.get(m.AnimalDecisionModel, ref)
            item.update(title='Decisión registrada', notes=d.reason, recorded_by=self.author(d.user_id))
            labels = {'retain_breeding':'Conservar para reproducción','exclude_breeding':'Descartar para reproducción','separate':'Separar','sale_planned':'Venta prevista','purchase_reason':'Motivo de compra','other':'Otra decisión'}
            detail('Decisión', labels.get(d.kind, d.kind))
        elif kind == 'event':
            e = self.get(m.EventModel, ref)
            item.update(notes=e.reason, recorded_by=self.author(e.user_id))
            if e.event_type_id == 1:
                item.update(title='Observación', notes=self.get(m.EventObservationModel, ref).observation)
            elif e.event_type_id == 2:
                d = self.get(m.EventDiagnosisModel, ref)
                item.update(title='Diagnóstico', notes=d.diagnosis)
                detail('Caso sanitario', self.get(m.HealthCaseModel, d.health_case_id).reason)
                detail('Gravedad', {'mild':'Leve','moderate':'Moderada','severe':'Grave','critical':'Crítica'}.get(d.severity,d.severity))
            elif e.event_type_id == 3:
                item['title'] = 'Tratamiento registrado'
                for t in self.db.scalars(select(m.EventTreatmentModel).where(m.EventTreatmentModel.event_id == ref)):
                    if t.health_case_id: detail('Caso sanitario', self.get(m.HealthCaseModel, t.health_case_id).reason)
                    detail('Producto', self.name(m.ProductModel, t.product_id))
                    detail('Dosis indicada', f'{t.dose_value} {self.get(m.UnitModel,t.dose_unit_id).code}')
                    detail('Vía', self.name(m.AdministrationRouteModel, t.route_id))
                    detail('Inicio / duración', f'{t.start_date} / {t.duration_days} días')
                    if t.program_id: detail('Programa sanitario', self.name(m.HealthProgramModel, t.program_id))
            elif e.event_type_id == 4:
                marker = self.get(m.EventWeaningModel, ref)
                item['title'] = 'Destete' if marker else 'Pesaje'
                detail('Peso (kg)', self.get(m.EventWeightModel, ref).weight_kg)
                if marker:
                    item.update(notes=marker.notes, recorded_by=self.author(marker.user_id))
                    detail('Edad al registrar', f'{(e.date.date()-marker.birth_date_snapshot).days} días' if marker.birth_date_snapshot else 'Desconocida')
            elif e.event_type_id == 5:
                t = self.get(m.EventMatingModel, ref)
                item['title'] = 'Monta'
                detail('Pareja', self.name(m.AnimalModel, t.male_id if e.animal_id == self.animal_id else e.animal_id))
            elif e.event_type_id == 6:
                item['title'] = 'Diagnóstico de gestación'
                detail('Resultado', {'pregnant':'Gestante','empty':'Vacía','uncertain':'Dudosa'}.get(self.get(m.EventPregnancyModel,ref).result, self.get(m.EventPregnancyModel,ref).result))
            elif e.event_type_id == 7:
                birth = self.get(m.EventBirthModel, ref)
                item.update(title='Parto' if e.animal_id == self.animal_id else 'Parto con descendencia', notes=birth.notes)
                detail('Tipo de parto', self.name(m.BirthTypeModel, birth.birth_type_id))
                children = select(m.AnimalModel).join(m.BirthOffspringModel, m.BirthOffspringModel.animal_id == m.AnimalModel.id).where(m.BirthOffspringModel.event_id == ref)
                if e.animal_id != self.animal_id: children = children.where(m.AnimalModel.father_id == self.animal_id)
                detail('Crías registradas', ', '.join(a.name or a.siniiga or a.id for a in self.db.scalars(children)))
            elif e.event_type_id == 8:
                item['title'] = 'Salida del hato'
                detail('Tipo', {'sale':'Venta','death':'Muerte','slaughter':'Sacrificio','transfer':'Traspaso','theft':'Robo','other':'Otra salida'}.get(self.get(m.ExitModel,ref).exit_type))
            else:
                item['title'] = 'Traslado de ubicación'
                detail('Destino', self.name(m.LocationModel, e.location_id))
        elif kind == 'case_open':
            c = self.get(m.HealthCaseModel, ref)
            item.update(title='Apertura de caso sanitario', notes=c.reason, recorded_by=self.initial_author('health_cases', ref))
            detail('Observaciones del caso', c.notes)
        elif kind == 'case_change':
            audit = self.get(m.AuditModel, ref)
            item.update(title='Cambio de estado del caso', recorded_by=self.author(audit.user_id))
            detail('Fecha de registro', 'UTC')
            labels = {'open':'Abierto','under_treatment':'En tratamiento','closed':'Cerrado'}
            detail('Antes', labels.get((audit.old_values or {}).get('status')))
            detail('Después', labels.get((audit.new_values or {}).get('status')))
            detail('Fecha de cierre', (audit.new_values or {}).get('closed_date'))
        elif kind == 'followup':
            f = self.get(m.CaseFollowupModel, ref)
            item.update(title='Seguimiento sanitario', notes=f.notes, recorded_by=self.author(f.user_id))
            detail('Caso sanitario', self.get(m.HealthCaseModel, f.health_case_id).reason)
            detail('Evolución', {'improved':'Mejoró','unchanged':'Sin cambios','worsened':'Empeoró','recovered':'Recuperado'}.get(f.evolution,f.evolution))
            detail('Resultado del tratamiento', {'not_assessed':'Sin evaluar','effective':'Efectivo','partially_effective':'Parcialmente efectivo','not_effective':'No efectivo'}.get(f.treatment_result,f.treatment_result))
            detail('Próxima revisión', f.next_review_date)
        elif kind.startswith('group_'):
            item['title'] = 'Inicio de pertenencia al lote' if kind == 'group_start' else 'Fin de pertenencia al lote'
            detail('Lote', self.name(m.AnimalGroupModel, ref))
        elif kind == 'feeding':
            f = self.get(m.FeedingModel, ref)
            feed = self.get(m.FeedModel, f.feed_id)
            item.update(title='Alimentación del lote' if f.group_id else 'Alimentación individual', recorded_by=self.initial_author('feedings', ref))
            detail('Alimento', feed.name)
            detail('Cantidad del lote completo' if f.group_id else 'Cantidad', f'{f.quantity} {self.get(m.UnitModel,feed.unit_id).code}')
            if f.group_id:
                detail('Lote', self.name(m.AnimalGroupModel, f.group_id))
                item['notes'] = 'Consumo del lote durante la pertenencia registrada del animal; no es una cantidad individual.'
        elif kind == 'expense':
            expense = self.get(m.ExpenseModel, ref)
            item.update(title='Gasto atribuido al animal', notes=expense.description, recorded_by=self.initial_author('expenses', ref))
            cases = select(m.HealthCaseModel.id).where(m.HealthCaseModel.animal_id == self.animal_id)
            allocations = self.db.scalars(select(m.ExpenseAllocationModel).where(m.ExpenseAllocationModel.expense_id == ref,
                or_(m.ExpenseAllocationModel.animal_id == self.animal_id, m.ExpenseAllocationModel.health_case_id.in_(cases))))
            detail('Porcentaje atribuido', sum(a.percentage for a in allocations))
            detail('Importe total del gasto (MXN)', expense.amount)
        else:
            income = self.get(m.IncomeModel, ref)
            item.update(title='Ingreso vinculado a la venta', notes=income.description, recorded_by=self.initial_author('incomes', ref))
            detail('Importe (MXN)', income.amount)
        return item


@router.get('/{animal_id}/timeline')
def timeline(animal_id: UUID, module: Module | None = None, date_from: date | None = None, date_to: date | None = None,
             offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
             actor=Depends(require_permission('animals:read')), db: Session = Depends(get_db, scope='function')):
    if date_from and date_to and date_from > date_to:
        raise ApplicationError('Invalid report date range', 422)
    permissions = actor.role.permissions
    if module and module+':read' not in permissions:
        raise ApplicationError('Insufficient permissions', 403)
    animal_id = str(animal_id)
    if db.get(m.AnimalModel, animal_id) is None:
        raise ApplicationError('Animal not found', 404)
    queries = sources(animal_id, permissions)
    combined = union_all(*queries).subquery()
    recorded = combined.c.kind.in_(['registration', 'case_change'])
    query = select(combined).where(or_(
        recorded & (combined.c.date <= str(datetime.now(timezone.utc).replace(tzinfo=None))),
        ~recorded & (combined.c.date <= date.today().isoformat()+' 23:59:59.999999')))
    if module: query = query.where(combined.c.module == module)
    if date_from: query = query.where(combined.c.date >= date_from.isoformat())
    if date_to: query = query.where(combined.c.date <= date_to.isoformat()+' 23:59:59.999999')
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(query.order_by(combined.c.date.desc(), combined.c.module, combined.c.kind, combined.c.reference).offset(offset).limit(limit))
    service = Timeline(db, animal_id, permissions)
    return dict(items=[service.response(row) for row in rows], total=total, offset=offset, limit=limit,
                modules=[name for name in get_args(Module) if name+':read' in permissions], date_from=date_from, date_to=date_to)
