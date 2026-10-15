from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel

AuditModule = Literal['animals', 'health', 'breeding', 'weights', 'exits', 'finance',
                      'feeding', 'locations', 'groups', 'users', 'roles', 'other']
AuditAction = Literal['INSERT', 'UPDATE', 'DELETE']


class AuditActor(BaseModel):
    id: str
    name: str
    email: str
    active: bool


class AuditSummary(BaseModel):
    id: str
    date: datetime
    actor: AuditActor | None
    module: AuditModule
    table: str
    record_id: str
    record_name: str | None
    event_type_id: int | None
    action: AuditAction


class AuditPage(BaseModel):
    items: list[AuditSummary]
    total: int
    offset: int
    limit: int


class AuditChange(BaseModel):
    field: str
    before_present: bool
    after_present: bool
    before: Any = None
    after: Any = None
    before_label: str | None = None
    after_label: str | None = None


class AuditDetail(AuditSummary):
    old_values: dict | None
    new_values: dict | None
    changes: list[AuditChange]
