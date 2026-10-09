"""Effective exits are derived from events, never stored as animal flags."""
from datetime import date, datetime, time
from sqlalchemy import exists, select
from sqlalchemy.orm import aliased
from src.core.errors import ApplicationError
from src.core.models import EventModel, ExitModel


def effective_exit_query():
    replacement = aliased(EventModel)
    return select(EventModel, ExitModel).join(ExitModel, ExitModel.event_id == EventModel.id).where(
        ~exists(select(replacement.id).where(replacement.replaced_event_id == EventModel.id)))


def has_exited(animal_id, day=None):
    statement = effective_exit_query().where(EventModel.animal_id == animal_id)
    if day is not None:
        statement = statement.where(EventModel.date <= datetime.combine(day, time.max))
    return exists(statement)


def ensure_in_herd(db, animal_id, day):
    # With date-only inputs, same-day activity can precede the exit.
    if db.scalar(effective_exit_query().with_only_columns(EventModel.id).where(
            EventModel.animal_id == animal_id, EventModel.date < datetime.combine(day, time.min)).limit(1).with_for_update()):
        raise ApplicationError('Activity date is after animal exit', 409)


def exit_state(db, animal_id):
    row = db.execute(effective_exit_query().where(
        EventModel.animal_id == animal_id, EventModel.date <= datetime.combine(date.today(), time.max)
    ).order_by(EventModel.date.desc(), EventModel.id).limit(1)).first()
    return (row[1].exit_type, row[0].date.date()) if row else ('active', None)
