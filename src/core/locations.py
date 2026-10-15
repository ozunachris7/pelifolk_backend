"""Physical location is derived from effective events, independently of group membership."""
from datetime import date, datetime, time
from sqlalchemy import exists, select
from sqlalchemy.orm import aliased
from src.core.models import AnimalModel, EventModel, LocationModel
from src.core.herd import has_exited


def effective_location_query():
    replacement = aliased(EventModel)
    return select(EventModel).where(EventModel.location_id.is_not(None),
        ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id)))


def latest_location_event_id():
    return (effective_location_query().with_only_columns(EventModel.id).where(
        EventModel.animal_id == AnimalModel.id, EventModel.date <= datetime.combine(date.today(), time.max))
        .order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc()).limit(1).correlate(AnimalModel).scalar_subquery())


def location_summary(location, event):
    if location is None: return None
    return dict(id=location.id, name=location.name, active=location.active, since=event.date.date())


def current_location(db, animal_id):
    if db.scalar(select(AnimalModel.id).where(AnimalModel.id == animal_id, has_exited(AnimalModel.id, date.today()))): return None
    event = db.scalar(effective_location_query().where(EventModel.animal_id == animal_id,
        EventModel.date <= datetime.combine(date.today(), time.max)).order_by(EventModel.date.desc(), EventModel.created_at.desc(), EventModel.id.desc()).limit(1))
    return location_summary(db.get(LocationModel, event.location_id), event) if event else None
