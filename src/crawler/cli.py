import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from .config import load_config
from .ids import generate_ids
from .progress import ProgressStore
from .pipeline import run_pipeline

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init','run','resume','status','retry-failed','recheck-not-found','export'])
    parser.add_argument('--config',type=Path,default=Path('config/crawler.yaml'))
    parser.add_argument('--run-id')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--stages',nargs='+',choices=['arxiv','s2'],default=['arxiv','s2'])
    parser.add_argument('--takeover-stale',action='store_true')
    args=parser.parse_args(); config=load_config(args.config)
    if args.command in ('run','resume'):
        print(json.dumps(asyncio.run(run_pipeline(config,set(args.stages),args.command=='resume',limit=args.limit,takeover_stale=args.takeover_stale)),indent=2)); return
    if args.command=='export':
        from .export import export_snapshot
        if not args.run_id: parser.error('--run-id required')
        print(json.dumps(export_snapshot(config,args.run_id),indent=2)); return
    store=ProgressStore(config.paths['persistent_root'])
    if args.command=='init': store.initialize(generate_ids(**config.range))
    elif args.command=='retry-failed': store.reset('failed')
    elif args.command=='recheck-not-found': store.reset('not_found')
    print(json.dumps(dict(Counter(f'{r["stage"]}:{r["status"]}' for r in store.rows.values())),indent=2))

if __name__=='__main__': main()
