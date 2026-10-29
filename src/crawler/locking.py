"""Local exclusion plus an explicit stale-run takeover marker for Drive datasets."""
import fcntl
import json
from pathlib import Path
from .storage import atomic_json
from .console import log

class DatasetLock:
    def __init__(self,root,run_id,takeover_stale=False):
        self.root=Path(root); self.run_id=run_id; self.takeover=takeover_stale; self.previous=None
    def __enter__(self):
        log('Lock: creating/checking dataset directory')
        self.root.mkdir(parents=True,exist_ok=True)
        log('Lock: opening writer.lock')
        self.file=(self.root/'writer.lock').open('a')
        try:
            log('Lock: acquiring local writer lock')
            fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.marker=self.root/'progress'/'active_run.json'
            log('Lock: checking previous active marker')
            if self.marker.exists():
                log('Lock: reading previous active marker')
                self.previous=json.loads(self.marker.read_text())
                if not self.takeover: raise RuntimeError('Previous active marker exists; stop the previous runtime before explicit takeover')
            log('Lock: publishing active marker')
            atomic_json(self.marker,dict(run_id=self.run_id,previous=self.previous))
            if self.previous:
                from datetime import datetime, timezone
                atomic_json(self.root/'progress'/'takeovers'/f'{self.run_id}.json',dict(run_id=self.run_id,previous=self.previous,captured_at=datetime.now(timezone.utc).isoformat()))
            log('Lock: acquired')
            return self
        except BaseException:
            self.file.close(); raise
    def __exit__(self,*args):
        log('Lock: releasing active marker')
        try: self.marker.unlink(missing_ok=True)
        finally: self.file.close()
