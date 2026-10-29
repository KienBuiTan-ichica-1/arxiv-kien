"""Immediate notebook diagnostics; callers supply no secrets or response bodies."""
from datetime import datetime, timezone

def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)
