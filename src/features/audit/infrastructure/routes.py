from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.features.auth.infrastructure.dependencies import require_permission
from src.features.audit.domain.dto import AuditActor, AuditAction, AuditModule, AuditPage, AuditDetail
from .repository import SQLAuditRepository

router = APIRouter(prefix='/audit', tags=['Audit'])


def repository(db: Session = Depends(get_db, scope='function')):
    return SQLAuditRepository(db)


def utc_boundary(value):
    if value is None:
        return None
    if value.tzinfo is None:
        raise ApplicationError('Audit date filters must include a timezone', 422)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get('/users', response_model=list[AuditActor])
def users(q: str = Query('', max_length=100), limit: int = Query(50, ge=1, le=100),
          actor=Depends(require_permission('audit:read')), repo=Depends(repository)):
    return repo.users(q.strip(), limit)


@router.get('', response_model=AuditPage)
def listing(q: str = Query('', max_length=100), module: AuditModule | None = None,
            action: AuditAction | None = None, user_id: UUID | Literal['system'] | None = None,
            date_from: datetime | None = None, date_before: datetime | None = None,
            record_id: str | None = Query(None, min_length=1, max_length=100),
            table: str | None = Query(None, min_length=1, max_length=64),
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
            actor=Depends(require_permission('audit:read')), repo=Depends(repository)):
    start, end = utc_boundary(date_from), utc_boundary(date_before)
    if start and end and start >= end:
        raise ApplicationError('Audit date range is invalid', 422)
    return repo.page(q.strip(), module, action, user_id, start, end, record_id, table, offset, limit)


@router.get('/{audit_id}', response_model=AuditDetail)
def detail(audit_id: UUID, actor=Depends(require_permission('audit:read')), repo=Depends(repository)):
    return repo.detail(str(audit_id))
