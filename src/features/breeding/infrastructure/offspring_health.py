"""Permission-gated case counts for the offspring birth cohort; no causal or genetic scoring."""
from datetime import date
from sqlalchemy import func, select
from src.core.models import HealthCaseModel
from src.core.errors import ApplicationError
from .repository import SQLBreedingRepository


def case_counts():
    return dict(total_cases=0, open_cases=0, under_treatment_cases=0, closed_cases=0)


def parent_counts():
    return dict(**case_counts(), offspring_with_cases=0, offspring_without_cases=0)


def collect_case_counts(db, child_ids):
    counts = {key:case_counts() for key in child_ids}
    if child_ids:
        query = select(HealthCaseModel.animal_id, HealthCaseModel.status, func.count()).where(
            HealthCaseModel.animal_id.in_(child_ids), HealthCaseModel.start_date <= date.today()).group_by(HealthCaseModel.animal_id, HealthCaseModel.status)
        for child_id, status, total in db.execute(query):
            counts[child_id]['total_cases'] += total
            counts[child_id][{'open':'open_cases','under_treatment':'under_treatment_cases','closed':'closed_cases'}[status]] += total
    return counts


def case_page(db, parent_id, child_id, filters, offset, limit):
    repo = SQLBreedingRepository(db)
    parent, child = repo.animal(parent_id), repo.animal(child_id)
    relation = child.mother_id if parent.sex == 'female' else child.father_id
    if relation != parent.id or child.birth_date and child.birth_date > date.today():
        raise ApplicationError('Offspring is not in this performance cohort', 404)
    if (filters['date_from'] and (not child.birth_date or child.birth_date < filters['date_from']) or
            filters['date_to'] and (not child.birth_date or child.birth_date > filters['date_to'])):
        raise ApplicationError('Offspring is not in this performance cohort', 404)
    query = select(HealthCaseModel).where(HealthCaseModel.animal_id == child.id, HealthCaseModel.start_date <= date.today())
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(HealthCaseModel.start_date.desc(), HealthCaseModel.id).offset(offset).limit(limit))
    return dict(parent=repo.summary(parent), animal=repo.summary(child), as_of=date.today(), **filters,
                items=[dict(id=c.id, reason=c.reason, status=c.status, start_date=c.start_date, closed_date=c.closed_date) for c in rows],
                total=total, offset=offset, limit=limit)
