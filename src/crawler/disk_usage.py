"""Logical dataset-byte counters: one baseline scan, then changed-subtree updates."""
from pathlib import Path


class DiskUsage:
    def __init__(self,roots):
        roots=sorted({Path(p).resolve() for p in roots},key=lambda p:(len(p.parts),str(p)))
        self.roots=[]
        for root in roots:
            if not any(root==r or r in root.parents for r in self.roots): self.roots.append(root)
        self.sizes={}; self.members={}; self.total=0
        self.reconcile()

    def reconcile(self):
        self.sizes={}; self.members={}; self.total=0
        for root in self.roots: self.touch(root)

    def touch(self,path):
        path=Path(path).resolve()
        if not any(path==r or r in path.parents for r in self.roots): return
        previous=[path] if path in self.sizes else list(self.members.get(path,()))
        for p in previous:
            self.total-=self.sizes.pop(p)
            for parent in p.parents:
                if parent in self.members:
                    self.members[parent].discard(p)
                    if not self.members[parent]: del self.members[parent]
        paths=path.rglob('*') if path.is_dir() else [path]
        for p in paths:
            try:
                if p.is_file() and not p.is_symlink():
                    size=p.stat().st_size; self.sizes[p]=size; self.total+=size
                    for parent in p.parents: self.members.setdefault(parent,set()).add(p)
            except FileNotFoundError: pass
