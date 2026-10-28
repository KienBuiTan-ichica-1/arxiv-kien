import json
import re
from pathlib import Path
from dataclasses import asdict
import hashlib
import pyarrow as pa
import pyarrow.parquet as pq
from .progress import ProgressStore
from .storage import atomic_json,digest

PAPER_SCHEMA=pa.schema([pa.field('arxiv_id',pa.string(),False),pa.field('title',pa.string()),pa.field('authors',pa.list_(pa.string())),pa.field('submission_date',pa.string()),pa.field('revised_dates',pa.list_(pa.string())),pa.field('venue',pa.string())])
REFERENCE_SCHEMA=pa.schema([pa.field('arxiv_id',pa.string(),False),pa.field('ref_arxiv_id',pa.string(),False),pa.field('ref_title',pa.string()),pa.field('ref_authors',pa.list_(pa.string())),pa.field('ref_submission_date',pa.string()),pa.field('ref_s2_id',pa.string())])

def export_snapshot(config,run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',run_id): raise ValueError('Invalid run ID')
    store=ProgressStore(config.paths['persistent_root'])
    target=Path(config.paths['persistent_root'])/'exports'/run_id
    target.mkdir(parents=True,exist_ok=False)
    papers=[]; references={}; missing=0; duplicates=0
    for key in sorted(store.rows):
        if key[2]!='discovery': continue
        paper=key[0]; meta={}; revisions=[]
        if store.storage.verify(key): meta=json.loads((store.storage.result_dir(key)/'normalized.json').read_text())
        else: missing+=1
        for version in range(2,meta.get('version',0)+1):
            vkey=(paper,version,'metadata',0)
            if store.storage.verify(vkey):
                value=json.loads((store.storage.result_dir(vkey)/'normalized.json').read_text()).get('updated')
                if value: revisions.append(value)
        papers.append(dict(arxiv_id=paper,title=meta.get('title'),authors=meta.get('authors'),submission_date=meta.get('published'),revised_dates=revisions if meta else None,venue=meta.get('venue')))
        rkey=(paper,0,'references',0)
        if not store.storage.verify(rkey): continue
        snapshot=json.loads((store.storage.result_dir(rkey)/'normalized.json').read_text())
        for ref in snapshot['references']:
            if not ref.get('ref_arxiv_id'): continue
            row={field.name:ref.get(field.name) for field in REFERENCE_SCHEMA}; row['arxiv_id']=paper
            unique=(paper,row['ref_arxiv_id'])
            if unique in references: duplicates+=1
            previous=references.get(unique)
            rank=lambda r:(sum(v is not None for v in r.values()),json.dumps(r,sort_keys=True))
            if previous is None or rank(row)>rank(previous): references[unique]=row
    pq.write_table(pa.Table.from_pylist(papers,schema=PAPER_SCHEMA),target/'papers.parquet')
    pq.write_table(pa.Table.from_pylist(list(references.values()),schema=REFERENCE_SCHEMA),target/'references.parquet')
    manifest=dict(schema_version=1,run_id=run_id,papers=len(papers),references=len(references),missing_metadata=missing,duplicate_references=duplicates,config_fingerprint=hashlib.sha256(json.dumps(asdict(config),sort_keys=True).encode()).hexdigest(),checksums={p.name:digest(p) for p in target.iterdir()})
    atomic_json(target/'manifest.json',manifest)
    return manifest
