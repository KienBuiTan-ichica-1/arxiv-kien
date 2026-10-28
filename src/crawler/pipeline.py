"""Two independently paced service branches, sharing durable progress."""
import asyncio
import fcntl
import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
import httpx
from .ids import generate_ids
from .progress import ProgressStore
from .storage import atomic_json, digest
from .scheduler import Scheduler
from .secrets import load_semantic_scholar_key
from .arxiv_client import parse_atom
from .semantic_scholar import parse_page,FIELDS
from .sources import inspect_and_extract

async def run_pipeline(config,stages=None,resume=True,*,limit=10,takeover_stale=False,transport=None):
    config.validate(); stages=stages or {'arxiv','s2'}
    ids=generate_ids(**config.range)
    if limit is not None:
        if limit<1: raise ValueError('limit must be positive')
        selected=set(ids[:limit])
    else: selected=set(ids)
    root=Path(config.paths['persistent_root']); root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<config.execution['min_free_disk_bytes']: raise OSError('Insufficient disk space')
    lock=(root/'writer.lock').open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close(); raise RuntimeError('Dataset has an active writer') from None
    active=root/'progress'/'active_run.json'
    if active.exists() and not takeover_stale:
        lock.close(); raise RuntimeError('Previous run marker exists; confirm old runtime stopped, then takeover_stale=True')
    run_id=uuid.uuid4().hex; started=time.monotonic()
    api_key=load_semantic_scholar_key() if 's2' in stages else None
    if 's2' in stages and not api_key and not config.execution['allow_anonymous_s2']:
        lock.close(); raise RuntimeError('Set API key or explicitly allow anonymous S2')
    store=ProgressStore(root); store.initialize(ids); store.reconcile()
    atomic_json(active,dict(run_id=run_id))
    scratch=Path(config.paths['scratch_root'])/run_id
    scratch.mkdir(parents=True,exist_ok=True)
    async def metadata(key,scheduler):
        raw=await scheduler.request(key,'arxiv','https://export.arxiv.org/api/query',params={'id_list':key[0]+(f'v{key[1]}' if key[1] else '')},validate=lambda raw:(raw,parse_atom(raw,key[0],key[1] or None)))
        if raw is None: return
        raw,parsed=raw
        if parsed.get('not_found'): store.finish(key,'not_found'); return
        staging=scratch/f'{key[0]}-v{key[1]}-{key[2]}'
        staging.mkdir(parents=True,exist_ok=True)
        (staging/'response.xml').write_bytes(raw); atomic_json(staging/'normalized.json',parsed)
        store.storage.commit(key,staging); store.reconcile()
    async def arxiv(scheduler):
        discovery_turn=True
        while 'arxiv' not in scheduler.stopped:
            discoveries=[k for k in store.pending('discovery') if k[0] in selected]
            versions=sorted([k for s in ('metadata','source') for k in store.pending(s) if k[0] in selected],key=lambda k:(k[0],k[1],k[2]=='source'))
            if not discoveries and not versions: break
            if discoveries and (discovery_turn or not versions):
                key=discoveries[0]; discovery_turn=False
            else: key=versions[0]; discovery_turn=True
            if key[2]!='source': await metadata(key,scheduler); continue
            archive=scratch/f'{key[0]}v{key[1]}.download'
            staging=scratch/f'{key[0]}v{key[1]}-source'
            try:
                result=await scheduler.request(key,'arxiv',f'https://export.arxiv.org/src/{key[0]}v{key[1]}',target=archive,validate=lambda p:inspect_and_extract(p,staging,config))
            except RuntimeError as exc:
                if str(exc)!='resource_limit': raise
                store.finish(key,'failed','resource_limit'); continue
            if result:
                store.storage.commit(key,staging,result['status']); store.finish(key,result['status']); archive.unlink(missing_ok=True)
    async def references(scheduler):
        for paper in ids:
            if paper not in selected or 's2' in scheduler.stopped: continue
            base=(paper,0,'references',0)
            if store.get(base)['status'] in ('succeeded','failed','not_found'): continue
            offset=0; refs=[]; unresolved=0
            fingerprint=hashlib.sha256(f'{FIELDS}:{config.network["s2_page_size"]}'.encode()).hexdigest()
            staging=store.storage.paper_dir(paper)/'reference-staging'/fingerprint
            staging.mkdir(parents=True,exist_ok=True)
            while True:
                key=(paper,0,'references',offset)
                store.add(key); store.save()
                page_path=staging/f'page-{offset:06d}.json'
                marker_path=staging/f'page-{offset:06d}.complete.json'
                cached=False
                if marker_path.exists() and page_path.exists():
                    marker=json.loads(marker_path.read_text())
                    cached=marker.get('sha256')==digest(page_path) and marker.get('fingerprint')==fingerprint
                if cached:
                    raw=page_path.read_bytes(); page=parse_page(raw,offset)
                else:
                    raw=await scheduler.request(key,'s2',f'https://api.semanticscholar.org/graph/v1/paper/ARXIV:{paper}/references',params={'fields':FIELDS,'limit':config.network['s2_page_size'],'offset':offset},validate=lambda raw:(raw,parse_page(raw,offset)))
                    if raw is None:
                        store.finish(base,'failed' if store.get(key)['status']=='running' else store.get(key)['status'],store.get(key)['error']); break
                    raw,page=raw
                    page_path.write_bytes(raw)
                    atomic_json(marker_path,dict(sha256=digest(page_path),fingerprint=fingerprint))
                refs.extend(page['references']); unresolved+=page['unresolved_count']
                if page['next'] is None:
                    atomic_json(staging/'normalized.json',dict(references=refs,unresolved_count=unresolved))
                    store.storage.commit(base,staging); store.finish(base,'succeeded'); break
                offset=page['next']
    try:
        timeout=httpx.Timeout(config.network['read_timeout_seconds'],connect=config.network['connect_timeout_seconds'])
        async with httpx.AsyncClient(timeout=timeout,transport=transport,follow_redirects=False) as client:
            scheduler=Scheduler(config,store,client,api_key=api_key)
            async with asyncio.TaskGroup() as group:
                if 'arxiv' in stages: group.create_task(arxiv(scheduler))
                if 's2' in stages: group.create_task(references(scheduler))
    finally:
        summary=dict(run_id=run_id,jobs=len(store.rows),wall_seconds=time.monotonic()-started,authentication='key' if api_key else 'anonymous')
        atomic_json(root/'metrics'/run_id/'summary.json',summary)
        active.unlink(missing_ok=True); lock.close()
    return summary
