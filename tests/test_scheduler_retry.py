import asyncio
import httpx
from crawler.scheduler import Scheduler
from crawler.config import CrawlerConfig
from crawler.progress import ProgressStore

def test_last_429_persists(tmp_path):
    async def check():
        store=ProgressStore(tmp_path); store.initialize(['2504.02523'])
        key=('2504.02523',0,'discovery',0)
        clock=[1000.0]
        async def sleep(n): clock[0]+=n
        transport=httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':'100'}))
        async with httpx.AsyncClient(transport=transport) as client:
            s=Scheduler(CrawlerConfig(),store,client,now=lambda:clock[0],sleep=sleep)
            result=await s.request(key,'arxiv','https://export.arxiv.org/api/query')
            assert result is None
            assert store.get(key)['attempts']==3
            assert s.state['arxiv']['deadline']>=clock[0]+100
            other=Scheduler(CrawlerConfig(),store,client,now=lambda:clock[0],sleep=sleep)
            assert other.state==s.state
    asyncio.run(check())
