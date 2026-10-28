"""Inspect retained source payloads without network calls or changing progress."""
import gzip
import json
import tarfile
import zlib
from pathlib import Path
from .storage import digest
from .progress import ProgressStore


def inspect_payload(path):
    path=Path(path)
    result={'path':path.as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)}
    try:
        with path.open('rb') as stream: prefix=stream.read(65536)
        if prefix.startswith(b'\x1f\x8b'):
            result['container']='gzip'
            with gzip.open(path,'rb') as stream: prefix=stream.read(65536)
        if prefix.lstrip().lower().startswith((b'<!doctype html',b'<html')):
            result['payload']='html'
        elif prefix.startswith(b'%PDF-'):
            result['payload']='pdf'
        elif tarfile.is_tarfile(path):
            result['payload']='tar'
            with tarfile.open(path,'r:*') as archive:
                members=[]
                for member in archive:
                    if len(members)>=50: break
                    members.append({'name':member.name,'size':member.size,'regular':member.isfile(),'directory':member.isdir()})
                result['members_sample']=members
        elif any(token in prefix for token in (b'\\documentclass',b'\\documentstyle',b'\\begin{document}',b'\\input',b'\\def')):
            result['payload']='tex_candidate'
        else:
            result['payload']='unrecognized'
            result['signature_hex']=prefix[:16].hex()
    except (OSError,EOFError,zlib.error,tarfile.TarError) as exc:
        result['inspection_error']=type(exc).__name__
    return result


def diagnose_sources(config):
    store=ProgressStore(config.paths['persistent_root'])
    scratch=Path(config.paths['scratch_root'])
    reports=[]
    for key,row in store.rows.items():
        if key[2]!='source' or row['status']!='failed': continue
        files=sorted(scratch.glob(f'*/{key[0]}v{key[1]}.download'))
        reports.append({'paper':key[0],'version':key[1],'error':row['error'],'attempts':row['attempts'],'retained_payloads':[inspect_payload(p) for p in files]})
    return reports
