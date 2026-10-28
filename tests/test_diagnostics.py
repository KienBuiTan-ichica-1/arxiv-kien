import asyncio
import httpx
from crawler.config import CrawlerConfig
from crawler.progress import ProgressStore
from crawler.scheduler import Scheduler

def test_transport_error_preserves_type(tmp_path):
    async def run():
        store=ProgressStore(tmp_path); store.initialize(['2504.02523'])
        async def sleep(seconds): clock[0]+=seconds
        clock=[1000.0]
        def handler(request): raise httpx.ReadTimeout('sensitive upstream message')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            scheduler=Scheduler(CrawlerConfig(),store,client,now=lambda:clock[0],sleep=sleep)
            key=('2504.02523',0,'discovery',0)
            await scheduler.request(key,'arxiv','https://export.arxiv.org/api/query')
            assert store.get(key)['error']=='transport_ReadTimeout'
            assert store.get(key)['attempts']==3
    asyncio.run(run())

def test_payload_error_preserves_reason(tmp_path):
    async def run():
        store=ProgressStore(tmp_path); store.initialize(['2504.02523'])
        clock=[1000.0]
        async def sleep(seconds): clock[0]+=seconds
        def validate(raw): raise ValueError('Unrecognized source payload')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'<html/>'))) as client:
            scheduler=Scheduler(CrawlerConfig(),store,client,now=lambda:clock[0],sleep=sleep)
            key=('2504.02523',0,'discovery',0)
            await scheduler.request(key,'arxiv','https://export.arxiv.org/api/query',validate=validate)
            assert store.get(key)['error']=='payload_unrecognized'
    asyncio.run(run())

def test_offline_inspection(tmp_path):
    from crawler.diagnostics import inspect_payload
    p=tmp_path/'payload'; p.write_bytes(b'<html>server error</html>')
    assert inspect_payload(p)['payload']=='html'
    p.write_bytes(b'%PDF-1.4\n')
    assert inspect_payload(p)['payload']=='pdf'
