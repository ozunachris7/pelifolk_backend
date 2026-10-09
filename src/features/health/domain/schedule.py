from datetime import timedelta

def next_application(birth_date, minimum_age, last_application, interval, notice, today):
    first = birth_date + timedelta(days=minimum_age) if birth_date else None
    due = last_application + timedelta(days=interval) if last_application else first
    if due and first:
        due = max(due, first)
    if due is None:
        return None, None, 'missing_birth_date'
    remaining = (due-today).days
    status = 'overdue' if remaining<0 else 'due' if remaining==0 else 'upcoming' if remaining<=notice else 'scheduled'
    return due, remaining, status
