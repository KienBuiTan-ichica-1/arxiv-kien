"""Explicit resumable integrity audit; never changes crawl job statuses."""
import uuid
from .locking import DatasetLock
from .progress import ProgressStore
from .storage import atomic_json

def audit(config, *, ids=None, stages=None, full=False, takeover_stale=False, report=print):
    root=config.paths['persistent_root']
    with DatasetLock(root, 'audit-'+uuid.uuid4().hex, takeover_stale):
        store=ProgressStore(root)
        # A full audit has a durable identity so restarting full=True resumes it.
        session=store.root/'progress'/'audit.json'
        import json
        scope=dict(ids=sorted(ids) if ids is not None else None,
                   stages=sorted(stages) if stages is not None else None)
        state=json.loads(session.read_text()) if session.exists() else {}
        if full and (state.get('complete',True) or state.get('scope')!=scope):
            state=dict(complete=False,scope=scope,done={})
            atomic_json(session,state)
        keys=[k for k,r in store.rows.items() if k[3]==0
              and r['status'] in ('succeeded','no_tex','not_found')
              and (ids is None or k[0] in ids) and (stages is None or k[2] in stages)]
        counts=dict(verified=0,skipped=0,invalid=0)
        from .storage import digest
        for index,key in enumerate(keys,1):
            token=json.dumps(key)
            marker=store.storage.result_dir(key)/'complete.json'
            # Missing markers (e.g. HTTP 404 without a payload) are reported, not silently accepted.
            fingerprint=digest(marker) if marker.exists() else None
            skip=(store.storage.is_verified(key) if not full else
                  fingerprint is not None and state['done'].get(token)==fingerprint)
            if skip: counts['skipped']+=1
            elif store.storage.verify(key):
                store.storage.record_verification(key)
                counts['verified']+=1
                if full:
                    state['done'][token]=fingerprint
                    atomic_json(session,state)
            else: counts['invalid']+=1
            report(f'[Audit] {index}/{len(keys)} {key}: {counts}')
        if full:
            state['complete']=True
            atomic_json(session,state)
        return counts
