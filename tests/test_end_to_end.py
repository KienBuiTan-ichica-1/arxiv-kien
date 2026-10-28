import asyncio
import gzip
import httpx
from crawler.config import CrawlerConfig
from crawler.pipeline import run_pipeline
from crawler.progress import ProgressStore

class Body(httpx.AsyncByteStream):
    def __init__(self,data): self.data=data
    async def __aiter__(self):
        for offset in range(0,len(self.data),7): yield self.data[offset:offset+7]

def test_source_truncation_three_attempts_then_resume(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    c=CrawlerConfig(); c.execution['allow_anonymous_s2']=True; c.range['end_id']=2524
    calls=[]; clock=[1000.]
    async def sleep(n): clock[0]+=n
    tex=b'\\documentclass{article}\n\\includegraphics{figure}\n'
    archive=gzip.compress(tex)
    def handler(request):
        calls.append(str(request.url))
        if request.url.host=='api.semanticscholar.org': return httpx.Response(200,json={'data':[]})
        if request.url.path.startswith('/src/'):
            data=archive[:-6] if '02523' in request.url.path else archive
            return httpx.Response(200,stream=Body(data))
        papers=request.url.params['id_list'].split(',')
        entries=''.join(f'<entry><id>http://arxiv.org/abs/{paper.removesuffix("v1")}v1</id><title>T</title></entry>' for paper in papers)
        return httpx.Response(200,content=f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'.encode())
    result=asyncio.run(run_pipeline(c,limit=2,transport=httpx.MockTransport(handler),now=lambda:clock[0],sleep=sleep))
    store=ProgressStore('runtime')
    assert store.get(('2504.02523',1,'source',0))['error']=='payload_gzip_truncated'
    assert store.get(('2504.02523',1,'source',0))['attempts']==3
    assert store.get(('2504.02524',1,'source',0))['status']=='succeeded'
    before=len(calls)
    asyncio.run(run_pipeline(c,limit=2,transport=httpx.MockTransport(handler),now=lambda:clock[0],sleep=sleep))
    assert len(calls)==before
    assert result['status_counts']['references']['succeeded']==2
