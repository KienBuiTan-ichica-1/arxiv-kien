"""Canonical inclusive ID ranges with explicit bounds at month boundaries."""
from datetime import datetime
import re


def _month(value: str) -> datetime:
    if not isinstance(value,str) or not re.fullmatch(r'20\d{2}-(0[1-9]|1[0-2])',value):
        raise ValueError('Month must use YYYY-MM in 2000..2099')
    return datetime.strptime(value,'%Y-%m')


def _serial(value, label):
    if type(value) is not int or not 1<=value<=99999:
        raise ValueError(f'{label} must be an integer in 1..99999')
    return value


def generate_ids(start_month: str, start_id: int, end_month: str, end_id: int,
                 monthly_end_ids: dict[str,int] | None = None) -> list[str]:
    """Generate IDs without inventing the last serial of a calendar month.

    For a cross-month range, monthly_end_ids must supply a verified last serial
    for the start month and every intermediate month. The final month ends at
    end_id. The mapping is unnecessary for a same-month range.
    """
    first=_month(start_month); last=_month(end_month)
    start_id=_serial(start_id,'start_id'); end_id=_serial(end_id,'end_id')
    if first>last: raise ValueError('start_month must not be after end_month')
    if first==last and start_id>end_id: raise ValueError('Invalid inclusive ID range')
    bounds={} if monthly_end_ids is None else monthly_end_ids
    if not isinstance(bounds,dict): raise ValueError('monthly_end_ids must map YYYY-MM to last serial')
    for month,value in bounds.items():
        date=_month(month)
        if not first<=date<=last: raise ValueError(f'monthly_end_ids contains month outside range: {month}')
        _serial(value,f'monthly_end_ids[{month}]')
    months=[]; current=first
    while current<=last:
        months.append(current)
        if current==last: break
        current=current.replace(year=current.year+1,month=1) if current.month==12 else current.replace(month=current.month+1)
    for date in months[:-1]:
        name=date.strftime('%Y-%m')
        if name not in bounds: raise ValueError(f'Missing monthly_end_ids for {name}; provide the verified last serial, not 99999 by assumption')
    if first!=last and bounds[start_month]<start_id:
        raise ValueError('start_id exceeds the start month last serial')
    if end_month in bounds and end_id>bounds[end_month]:
        raise ValueError('end_id exceeds the final month last serial')
    ids=[]
    for index,date in enumerate(months):
        low=start_id if index==0 else 1
        high=end_id if date==last else bounds[date.strftime('%Y-%m')]
        ids.extend(f'{date:%y%m}.{serial:05d}' for serial in range(low,high+1))
    return ids
