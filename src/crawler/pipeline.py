"""Two independently paced service branches, sharing durable progress."""
import asyncio
from .locking import DatasetLock
from .metrics import MetricsRecorder, utc_now
from urllib.parse import quote
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
from .arxiv_client import parse_atom, parse_atom_batch
from .semantic_scholar import parse_page,FIELDS
from .sources import inspect_and_extract

async def _run_pipeline(config,stages=None,resume=True,*,limit=None,takeover_stale=False,transport=None,run_id=None,now=time.time,sleep=asyncio.sleep):
    config.validate(); stages=stages or {'arxiv','s2'}
    ids=generate_ids(**config.range)
    if limit is not None:
        if limit<1: raise ValueError('limit must be positive')
        selected=set(ids[:limit])
    else: selected=set(ids)
    root=Path(config.paths['persistent_root']); root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<config.execution['min_free_disk_bytes']: raise OSError('Insufficient disk space')
    started=time.monotonic()
    api_key=load_semantic_scholar_key() if 's2' in stages else None
    if 's2' in stages and not api_key and not config.execution['allow_anonymous_s2']:
        raise RuntimeError('Set API key or explicitly allow anonymous S2')
    store=ProgressStore(root); store.run_id=run_id; store.storage.run_id=run_id
    store.initialize(ids); store.reconcile()
    metrics=MetricsRecorder(config,'key' if api_key else 'anonymous'); metrics.start(run_id)
    metrics.record('recovery',counts=store.status_counts())
    monitor=asyncio.create_task(metrics.monitor())
    scratch=Path(config.paths['scratch_root'])/run_id
    scratch.mkdir(parents=True,exist_ok=True)
    async def metadata(key,scheduler):
        raw=await scheduler.request(key,'arxiv','https://export.arxiv.org/api/query',params={'id_list':key[0]+(f'v{key[1]}' if key[1] else '')},validate=lambda raw:(raw,parse_atom(raw,key[0],key[1] or None)))
        if raw is None: return
        raw,parsed=raw
        if parsed.get('not_found'): store.finish(key,'not_found'); return
        staging=scratch/f'{quote(key[0],safe="")}-v{key[1]}-{key[2]}'
        staging.mkdir(parents=True,exist_ok=True)
        (staging/'response.xml').write_bytes(raw); atomic_json(staging/'normalized.json',parsed)
        before=time.monotonic(); store.storage.commit(key,staging); store.reconcile(recover_running=False)
        metrics.record('commit',job=key,seconds=time.monotonic()-before)
    async def arxiv(scheduler):
        discovery_turn = True
        discovery_queue = asyncio.Queue(maxsize=config.execution['queue_capacity'])
        version_queue = asyncio.Queue(maxsize=config.execution['queue_capacity'])
        while 'arxiv' not in scheduler.stopped:
            pending_discoveries = [
                k for k in store.pending("discovery") if k[0] in selected
            ]
            if pending_discoveries:
                # Lấy 1 batch tối đa 50 ID
                batch = pending_discoveries[:50]
                await run_discovery_batch(batch, scheduler)
                continue  # Xong 1 batch discovery thì quay lại vòng lặp
            if discovery_queue.empty():
                for key in (k for k in store.pending('discovery') if k[0] in selected):
                    discovery_queue.put_nowait(key)
                    if discovery_queue.full(): 
                        break
            if version_queue.empty():
                keys=sorted([k for stage in ('metadata','source') for k in store.pending(stage) if k[0] in selected],key=lambda k:(k[0],k[1],k[2]=='source'))
                for key in keys[:config.execution['queue_capacity']]: version_queue.put_nowait(key)
            discoveries=not discovery_queue.empty(); versions=not version_queue.empty()
            if not discoveries and not versions: break
            if discoveries and (discovery_turn or not versions):
                key=discovery_queue.get_nowait(); discovery_turn=False
            else: key=version_queue.get_nowait(); discovery_turn=True
            if key[2]!='source': await metadata(key,scheduler); continue
            archive=scratch/f'{quote(key[0],safe="")}v{key[1]}.download'
            staging=scratch/f'{quote(key[0],safe="")}v{key[1]}-source'
            try:
                result=await scheduler.request(key,'arxiv',f'https://export.arxiv.org/src/{key[0]}v{key[1]}',target=archive,validate=lambda p:inspect_and_extract(p,staging,config))
            except RuntimeError as exc:
                if str(exc)!='resource_limit': raise
                store.finish(key,'failed','resource_limit'); continue
            if result:
                response_info=archive.with_suffix('.response.json')
                if response_info.exists(): shutil.copyfile(response_info,staging/'response.json')
                before=time.monotonic(); store.storage.commit(key,staging,result['status']); store.finish(key,result['status']); archive.unlink(missing_ok=True)
                metrics.record('commit',job=key,seconds=time.monotonic()-before)
                metrics.sample(force_disk=True)
    async def references(scheduler):
        for paper in ids:
            if paper not in selected or 's2' in scheduler.stopped: continue
            base=(paper,0,'references',0)
            if store.get(base)['status'] in ('succeeded','failed','not_found'): continue
            offset=0; refs=[]; unresolved=0
            fingerprint=hashlib.sha256(f'{FIELDS}:{config.network["s2_page_size"]}'.encode()).hexdigest()
            cache_root=store.storage.paper_dir(paper)/'reference-staging'
            if cache_root.exists() and any(d.is_dir() and d.name!=fingerprint for d in cache_root.iterdir()):
                store.finish(base,'failed','query_fingerprint_changed_refresh_required'); continue
            staging=cache_root/fingerprint
            staging.mkdir(parents=True,exist_ok=True)
            while True:
                key=(paper,0,'references',offset)
                store.add(key); store.save()
                page_path=staging/f'page-{offset:06d}.json'
                marker_path=staging/f'page-{offset:06d}.complete.json'
                cached=False
                if marker_path.exists() and page_path.exists():
                    try:
                        marker=json.loads(marker_path.read_text())
                        cached=marker.get('sha256')==digest(page_path) and marker.get('fingerprint')==fingerprint
                    except (OSError,ValueError): cached=False
                if cached:
                    raw=page_path.read_bytes(); page=parse_page(raw,offset)
                else:
                    raw=await scheduler.request(key,'s2',f'https://api.semanticscholar.org/graph/v1/paper/ARXIV:{paper}/references',params={'fields':FIELDS,'limit':config.network['s2_page_size'],'offset':offset},validate=lambda raw:(raw,parse_page(raw,offset)))
                    if raw is None:
                        store.finish(base,'not_found' if store.get(key)['status']=='not_found' else 'failed',store.get(key)['error'] or 'missing_page_result'); break
                    raw,page=raw
                    page_path.write_bytes(raw)
                    atomic_json(marker_path,dict(sha256=digest(page_path),fingerprint=fingerprint))
                if offset:
                    store.finish(key,'succeeded')
                refs.extend(page['references']); unresolved+=page['unresolved_count']
                if page['next'] is None:
                    atomic_json(staging/'normalized.json',dict(references=refs,unresolved_count=unresolved,fetched_at=utc_now(),query_fingerprint=fingerprint))
                    before=time.monotonic(); store.storage.commit(base,staging); store.reference_counts[paper]=len(refs); store.finish(base,'succeeded')
                    metrics.record('commit',job=base,seconds=time.monotonic()-before)
                    break
                offset=page['next']
                
    async def run_discovery_batch(batch_keys, scheduler):
        papers = [k[0] for k in batch_keys]
        id_list = ",".join(papers)
        # Quan trọng: arXiv mặc định max_results=10, nên phải truyền max_results=len(papers)
        raw = await scheduler.request(
            batch_keys,
            "arxiv",
            "https://export.arxiv.org/api/query",
            params={"id_list": id_list, "max_results": len(papers)},
            validate=lambda raw: (raw, parse_atom_batch(raw, papers)),
        )
        if raw is None:
            return
        raw, batch_parsed = raw
        for key in batch_keys:
            paper = key[0]
            parsed = batch_parsed.get(paper, {"not_found": True})
            if parsed.get("not_found"):
                store.finish(key, "not_found")
                continue
            staging = scratch / f'{quote(paper, safe="")}-discovery'
            staging.mkdir(parents=True, exist_ok=True)
            atomic_json(staging / "normalized.json", parsed)
            store.storage.commit(key, staging)
            store.finish(key, "succeeded")
            # Sinh các version jobs v1..vN cho bài vừa tìm thấy
            for v in range(1, parsed["version"] + 1):
                for stage in ("metadata", "source"):
                    store.add((paper, v, stage, 0))
        store.save(with_views=False)
    completed=False
    try:
        timeout=httpx.Timeout(config.network['read_timeout_seconds'],connect=config.network['connect_timeout_seconds'])
        async with httpx.AsyncClient(timeout=timeout,transport=transport,follow_redirects=False) as client:
            scheduler=Scheduler(config,store,client,api_key=api_key,metrics=metrics,now=now,sleep=sleep)
            async with asyncio.TaskGroup() as group:
                if 'arxiv' in stages: group.create_task(arxiv(scheduler))
                if 's2' in stages: group.create_task(references(scheduler))
        completed=True
    finally:
        monitor.cancel()
        try: await monitor
        except asyncio.CancelledError: 
            pass
        store.save(with_views=True)
        summary=metrics.stop(store,incomplete=not completed)
        summary['jobs']=len(store.rows)
    return summary


async def run_pipeline(config,stages=None,resume=True,*,limit=None,takeover_stale=False,transport=None,now=time.time,sleep=asyncio.sleep):
    run_id=uuid.uuid4().hex
    with DatasetLock(config.paths['persistent_root'],run_id,takeover_stale):
        return await _run_pipeline(config,stages,resume,limit=limit,takeover_stale=takeover_stale,transport=transport,run_id=run_id,now=now,sleep=sleep)
