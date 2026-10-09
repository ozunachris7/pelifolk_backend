from datetime import timedelta
from src.core.errors import ApplicationError


def close_period(start_date, effective_date):
    if effective_date <= start_date:
        raise ApplicationError('Movement date must be after current admission', 422)
    return effective_date - timedelta(days=1)
