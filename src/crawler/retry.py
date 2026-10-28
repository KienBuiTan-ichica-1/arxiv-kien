from email.utils import parsedate_to_datetime
from datetime import timezone

def parse_retry_after(value,now):
    if value is None: return None
    try: return max(0,float(value))
    except ValueError:
        try:
            date=parsedate_to_datetime(value)
            if date.tzinfo is None: date=date.replace(tzinfo=timezone.utc)
            return max(0,(date-now).total_seconds())
        except (ValueError,TypeError,OverflowError): return None
