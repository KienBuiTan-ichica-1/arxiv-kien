import json
import csv
import re
from pathlib import Path
from dataclasses import asdict
import hashlib
import pyarrow as pa
import pyarrow.parquet as pq
from .progress import ProgressStore
from .ids import generate_ids
from .storage import atomic_json,digest

PAPER_SCHEMA=pa.schema([pa.field('arxiv_id',pa.string(),False),pa.field('title',pa.string()),pa.field('authors',pa.list_(pa.string())),pa.field('submission_date',pa.string()),pa.field('revised_dates',pa.list_(pa.string())),pa.field('venue',pa.string()),pa.field('venue_source',pa.string()),pa.field('discovery_status',pa.string())])
REFERENCE_SCHEMA=pa.schema([pa.field('arxiv_id',pa.string(),False),pa.field('ref_arxiv_id',pa.string(),False),pa.field('ref_title',pa.string()),pa.field('ref_authors',pa.list_(pa.string())),pa.field('ref_submission_date',pa.string()),pa.field('ref_s2_id',pa.string())])

def _export_snapshot(config,run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id): raise ValueError('Invalid run ID')
    store=ProgressStore(config.paths['persistent_root'])
    target=Path(config.paths['persistent_root'])/'exports'/run_id
    target.mkdir(parents=True,exist_ok=False)
    selected=set(generate_ids(**config.range))
    for paper in sorted(selected):
        for stage in ('discovery','references'): store.add((paper,0,stage,0))
    cache={}
    def read_result(key, filename='normalized.json'):
        token=(key,filename)
        if token not in cache:
            cache[token]=None
            try:
                directory=store.storage.result_dir(key)
                marker=json.loads((directory/'complete.json').read_text())
                allowed=('succeeded','not_found') if key[2] in ('discovery','metadata') else ('succeeded','no_tex')
                if marker['key']!=list(key) or marker['status'] not in allowed: return None
                # Verify only the JSON consumed by export, never all source files.
                if digest(directory/filename)!=marker['checksums'][filename]: return None
                cache[token]=json.loads((directory/filename).read_text())
            except (OSError,ValueError,KeyError): pass
        return cache[token]
    venue_candidates={}
    for key in store.rows:
        if key[0] not in selected or key[2:]!=('references',0): continue
        snapshot=read_result(key)
        if snapshot:
            for ref in snapshot['references']:
                venue=ref.get('venue')
                if ref.get('ref_arxiv_id') and isinstance(venue,str) and venue.strip():
                    venue_candidates.setdefault(ref['ref_arxiv_id'],set()).add(venue.strip())
    papers=[]; references={}; missing=0; duplicates=0; conflicts=[]; revision_missing=0
    for key in sorted(store.rows):
        if key[2]!='discovery' or key[0] not in selected: continue
        paper=key[0]; meta={}; revisions=[]
        meta=read_result(key) or {}
        if store.rows[key]['status']!='succeeded' or not meta or meta.get('not_found'):
            missing+=1
            continue
        for version in range(2,meta.get('version',0)+1):
            vkey=(paper,version,'metadata',0)
            version_meta=read_result(vkey)
            if version_meta:
                value=version_meta.get('updated')
                if value: revisions.append(value)
                else: revision_missing+=1
            else: revision_missing+=1
        venues=venue_candidates.get(paper,set())
        venue=next(iter(venues)) if len(venues)==1 else None
        papers.append(dict(arxiv_id=paper,title=meta.get('title'),authors=meta.get('authors'),submission_date=meta.get('published'),revised_dates=revisions if meta else None,venue=venue,venue_source='semantic_scholar.citedPaper.venue' if venue else None,discovery_status='succeeded'))
        rkey=(paper,0,'references',0)
        snapshot=read_result(rkey)
        if not snapshot: continue
        for ref in snapshot['references']:
            if not ref.get('ref_arxiv_id'): continue
            row={field.name:ref.get(field.name) for field in REFERENCE_SCHEMA}; row['arxiv_id']=paper
            unique=(paper,row['ref_arxiv_id'])
            if unique in references:
                duplicates+=1
                if references[unique]!=row: conflicts.append(dict(arxiv_id=paper,ref_arxiv_id=row['ref_arxiv_id']))
            previous=references.get(unique)
            rank=lambda r:(sum(v is not None for v in r.values()),json.dumps(r,sort_keys=True))
            if previous is None or rank(row)>rank(previous): references[unique]=row
    pq.write_table(pa.Table.from_pylist(papers,schema=PAPER_SCHEMA),target/'papers.parquet')
    pq.write_table(pa.Table.from_pylist(list(references.values()),schema=REFERENCE_SCHEMA),target/'references.parquet')
    exported_ids={p['arxiv_id'] for p in papers}
    paper_metrics=[]; version_metrics=[]
    for key,row in store.rows.items():
        if key[0] not in selected: continue
        if key[2]=='discovery':
            refs=store.rows[(key[0],0,'references',0)]
            count=None
            ref_snapshot=read_result((key[0],0,'references',0))
            if ref_snapshot: count=len(ref_snapshot['references'])
            paper_metrics.append(dict(arxiv_id=key[0],discovery_status=row['status'],metadata_exported=key[0] in exported_ids,references_status=refs['status'],reference_count=count,discovery_attempts=row['total'],references_attempts=sum(r['total'] for k,r in store.rows.items() if k[0]==key[0] and k[2]=='references')))
        elif key[2]=='source':
            inventory={}
            inventory=read_result(key,'inventory.json') or {}
            version_metrics.append(dict(arxiv_id=key[0],version=key[1],source_status=row['status'],source_attempts=row['total'],error_code=row['error'],compressed_bytes=inventory.get('compressed_bytes'),unpacked_bytes=inventory.get('unpacked_bytes'),kept_bytes=inventory.get('kept_bytes'),tex_count=inventory.get('tex_count'),bib_count=inventory.get('bib_count')))
    for name,rows,columns in [
        ('paper_metrics',paper_metrics,['arxiv_id','discovery_status','metadata_exported','references_status','reference_count','discovery_attempts','references_attempts']),
        ('version_metrics',version_metrics,['arxiv_id','version','source_status','source_attempts','error_code','compressed_bytes','unpacked_bytes','kept_bytes','tex_count','bib_count'])]:
        with (target/f'{name}.csv').open('w',newline='',encoding='utf8') as f:
            writer=csv.DictWriter(f,fieldnames=columns); writer.writeheader(); writer.writerows(rows)
    run_summaries=[]
    for directory in (store.root/'metrics').glob('*'):
        path=directory/'summary.json'
        if not path.exists(): path=directory/'checkpoint.json'
        if path.exists(): run_summaries.append(json.loads(path.read_text()))
    atomic_json(target/'run_metrics.json',run_summaries)
    atomic_json(target/'reference_conflicts.json',conflicts)
    def mean(rows,field):
        values=[r[field] for r in rows if r.get(field) is not None]
        return dict(mean=sum(values)/len(values) if values else None,sample_count=len(values),missing_count=len(rows)-len(values))
    manifest=dict(schema_version=2,assigned_ids=len(selected),venue_conflicts=sorted(p for p,v in venue_candidates.items() if p in selected and len(v)>1),reference_date_source="semantic_scholar.publicationDate (not verified arXiv submission date)",integrity_scope="checksums of exported JSON only; full source audit is separate",run_id=run_id,papers=len(papers),references=len(references),missing_metadata=missing,missing_reference_snapshots=sum(r['reference_count'] is None for r in paper_metrics),valid_empty_reference_snapshots=sum(r['reference_count']==0 for r in paper_metrics),missing_revision_dates=revision_missing,duplicate_references=duplicates,conflicting_references=len(conflicts),config_fingerprint=hashlib.sha256(json.dumps(asdict(config),sort_keys=True).encode()).hexdigest(),input_fingerprint=hashlib.sha256(json.dumps(sorted(selected)).encode()).hexdigest(),schema_fingerprint=hashlib.sha256((str(PAPER_SCHEMA)+str(REFERENCE_SCHEMA)).encode()).hexdigest(),contributing_run_ids=[r['run_id'] for r in run_summaries],means=dict(reference_count=mean(paper_metrics,'reference_count'),compressed_bytes=mean(version_metrics,'compressed_bytes'),unpacked_bytes=mean(version_metrics,'unpacked_bytes'),kept_bytes=mean(version_metrics,'kept_bytes')),checksums={p.name:digest(p) for p in target.iterdir()})
    atomic_json(target/'manifest.json',manifest)
    return manifest


def export_snapshot(config,run_id):
    from .locking import DatasetLock
    import uuid
    with DatasetLock(config.paths['persistent_root'],'export-'+uuid.uuid4().hex):
        return _export_snapshot(config,run_id)
