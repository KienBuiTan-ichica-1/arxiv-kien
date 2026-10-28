import asyncio
import json
import time
from datetime import datetime, timezone
import httpx
from .retry import parse_retry_after
from .storage import atomic_json

class Scheduler:
    def __init__(self,config,store,client,now=time.time,sleep=asyncio.sleep,api_key=None):
        self.config=config; self.store=store; self.client=client; self.now=now; self.sleep=sleep; self.api_key=api_key
        self.path=store.root/'progress'/'services.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {s:dict(deadline=0,backoff=0,recent=[]) for s in ('arxiv','s2')}
        self.locks={s:asyncio.Lock() for s in self.state}; self.stopped=set()
    def persist(self): atomic_json(self.path,self.state)
    async def wait(self,deadline):
        while self.now()<deadline: await self.sleep(min(30,deadline-self.now()))
    async def request(self,key,service,url,params=None,target=None,validate=None):
        if service in self.stopped: return None
        net=self.config.network; state=self.state[service]
        gap=net['arxiv_gap_seconds'] if service=='arxiv' else net['s2_key_gap_seconds' if self.api_key else 's2_anonymous_gap_seconds']
        async with self.locks[service]:
            while self.store.get(key)['attempts']<3:
                deadline=state['deadline']
                if service=='s2' and not self.api_key:
                    recent=[t for t in state['recent'] if t>self.now()-net['s2_anonymous_window_seconds']]
                    state['recent']=recent
                    if len(recent)>=net['s2_anonymous_window_requests']: deadline=max(deadline,recent[0]+net['s2_anonymous_window_seconds'])
                await self.wait(deadline)
                self.store.start_attempt(key)
                state['recent'].append(self.now()); self.persist()
                headers={'User-Agent':net['user_agent']}
                if service=='s2' and self.api_key: headers['x-api-key']=self.api_key
                code=0
                try:
                    async with self.client.stream('GET',url,params=params,headers=headers,follow_redirects=False) as response:
                        code=response.status_code
                        if code==200:
                            if target:
                                target.parent.mkdir(parents=True,exist_ok=True)
                                with target.open('wb') as f:
                                    async for chunk in response.aiter_bytes(): f.write(chunk)
                                result=target
                            else:
                                result=await response.aread()
                            if validate: result=await asyncio.to_thread(validate,result)
                            state['backoff']=0
                            return result
                        retry_after=parse_retry_after(response.headers.get('Retry-After'),datetime.fromtimestamp(self.now(),timezone.utc))
                        if code==429:
                            state['backoff']=state['backoff']*2 or 60
                            state['deadline']=max(state['deadline'],self.now()+(retry_after if retry_after is not None else state['backoff']))
                        elif retry_after is not None:
                            state['deadline']=max(state['deadline'],self.now()+retry_after)
                        if code in (401,403): self.stopped.add(service)
                        if code not in (408,429) and code<500:
                            self.store.finish(key,'not_found' if code==404 else 'failed',f'http_{code}')
                            return None
                except (httpx.TransportError,ValueError):
                    code=0
                finally:
                    state['deadline']=max(state['deadline'],self.now()+gap); self.persist()
                attempt=self.store.get(key)['attempts']
                if attempt<3:
                    state['deadline']=max(state['deadline'],self.now()+net['retry_delays_seconds'][attempt-1]); self.persist()
                else: self.store.finish(key,'failed',f'http_{code}' if code else 'payload_or_transport')
            return None
