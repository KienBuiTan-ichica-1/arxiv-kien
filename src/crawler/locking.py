"""Local exclusion plus an explicit stale-run takeover marker for Drive datasets."""
import fcntl
import json
from pathlib import Path
from .storage import atomic_json

class DatasetLock:
    def __init__(self,root,run_id,takeover_stale=False):
        self.root=Path(root); self.run_id=run_id; self.takeover=takeover_stale; self.previous=None
    def __enter__(self):
        self.root.mkdir(parents=True,exist_ok=True)
        self.file=(self.root/'writer.lock').open('a')
        try:
            fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.marker=self.root/'progress'/'active_run.json'
            if self.marker.exists():
                self.previous=json.loads(self.marker.read_text())
                if not self.takeover: raise RuntimeError('Previous active marker exists; stop the previous runtime before explicit takeover')
            atomic_json(self.marker,dict(run_id=self.run_id,previous=self.previous))
            if self.previous:
                from datetime import datetime, timezone
                atomic_json(self.root/'progress'/'takeovers'/f'{self.run_id}.json',dict(run_id=self.run_id,previous=self.previous,captured_at=datetime.now(timezone.utc).isoformat()))
            return self
        except BaseException:
            self.file.close(); raise
    def __exit__(self,*args):
        try: self.marker.unlink(missing_ok=True)
        finally: self.file.close()
