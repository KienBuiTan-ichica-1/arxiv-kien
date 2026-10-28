"""Single-process progress writer; requests consume attempts before network I/O."""
import csv
import json
import os
import shutil
import threading
from pathlib import Path
from .storage import Storage, atomic_json, digest

class ProgressStore:
    columns=['paper','version','stage','offset','status','attempts','total','cycle','error']
    def __init__(self,root):
        self.root=Path(root); self.path=self.root/'progress'/'jobs.csv'
        self.lock=threading.RLock(); self.rows={}; self.storage=Storage(root)
        if self.path.exists() or self.path.with_suffix('.bak').exists(): self.load()
    def load(self):
        for path in (self.path,self.path.with_suffix('.bak')):
            try:
                manifest=json.loads(path.with_suffix(path.suffix+'.json').read_text())
                if digest(path)!=manifest['sha256']: raise ValueError('Invalid checksum')
                with path.open(newline='',encoding='utf8') as f:
                    reader=csv.DictReader(f)
                    if reader.fieldnames!=self.columns: raise ValueError('Invalid schema')
                    rows=list(reader)
                converted={}
                for r in rows:
                    for k in ('version','offset','attempts','total','cycle'): r[k]=int(r[k])
                    key=(r['paper'],r['version'],r['stage'],r['offset'])
                    if key in converted: raise ValueError('Duplicate job')
                    converted[key]=r
                if len(converted)!=manifest['count']: raise ValueError('Invalid row count')
                self.rows=converted; return
            except (OSError,ValueError,KeyError): continue
        raise RuntimeError('Progress and backup unavailable or corrupt; refusing empty dataset')
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',newline='',encoding='utf8') as f:
            w=csv.DictWriter(f,fieldnames=self.columns); w.writeheader(); w.writerows(self.rows.values())
            f.flush(); os.fsync(f.fileno())
        valid_current=False
        try:
            valid_current=digest(self.path)==json.loads(self.path.with_suffix('.csv.json').read_text())['sha256']
        except (OSError,ValueError,KeyError): pass
        if valid_current:
            shutil.copyfile(self.path,self.path.with_suffix('.bak'))
            shutil.copyfile(self.path.with_suffix('.csv.json'),self.path.with_suffix('.bak.json'))
        checksum=digest(tmp); tmp.replace(self.path)
        atomic_json(self.path.with_suffix('.csv.json'),dict(sha256=checksum,count=len(self.rows)))
        if digest(self.path)!=checksum: raise OSError('CSV readback failed')
    def add(self,key):
        if key not in self.rows:
            paper,version,stage,offset=key
            self.rows[key]=dict(paper=paper,version=version,stage=stage,offset=offset,status='pending',attempts=0,total=0,cycle=1,error='')
    def initialize(self,ids):
        with self.lock:
            for paper in ids:
                for stage in ('discovery','references'): self.add((paper,0,stage,0))
            self.save()
    def get(self,key): return self.rows[key]
    def pending(self,stage):
        return [k for k,r in self.rows.items() if k[2]==stage and r['status'] in ('pending','running') and r['attempts']<3]
    def start_attempt(self,key):
        with self.lock:
            row=self.rows[key]
            if row['attempts']>=3: raise RuntimeError('Attempt budget exhausted')
            row['attempts']+=1; row['total']+=1; row['status']='running'; self.save()
    def finish(self,key,status,error=''):
        with self.lock:
            self.rows[key].update(status=status,error=error); self.save()
    def reconcile(self):
        with self.lock:
            for key,row in list(self.rows.items()):
                marker=self.storage.verify(key)
                if marker:
                    row['status']=marker['status']
                    if key[2]=='discovery':
                        meta=json.loads((self.storage.result_dir(key)/'normalized.json').read_text())
                        for v in range(1,meta['version']+1):
                            for stage in ('metadata','source'): self.add((key[0],v,stage,0))
                elif row['status'] in ('running','succeeded','no_tex'):
                    row['status']='pending' if row['attempts']<3 else 'failed'
                    row['error']='integrity_missing_result'
            self.save()
    def reset(self,status='failed'):
        with self.lock:
            for row in self.rows.values():
                if row['status']==status: row.update(status='pending',attempts=0,cycle=row['cycle']+1,error='')
            self.save()
