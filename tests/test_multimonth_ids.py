import pytest
from crawler.ids import generate_ids
from crawler.config import load_config


def test_two_months_with_verified_month_end():
    assert generate_ids('2025-04',8,'2025-05',3,monthly_end_ids={'2025-04':10})==[
        '2504.00008','2504.00009','2504.00010','2505.00001','2505.00002','2505.00003']


def test_year_rollover_and_intermediate_month():
    assert generate_ids('2025-12',2,'2026-02',1,monthly_end_ids={'2025-12':3,'2026-01':2})==[
        '2512.00002','2512.00003','2601.00001','2601.00002','2602.00001']


@pytest.mark.parametrize('bounds', [None,{}, {'2025-04':9}])
def test_missing_intermediate_bound_is_explicit(bounds):
    with pytest.raises(ValueError,match='2025-05'):
        generate_ids('2025-04',2,'2025-06',1,monthly_end_ids=bounds or {'2025-04':9})


@pytest.mark.parametrize('bounds',[{'2025-04':1},{'2025-04':100000},{'2025-04':True},{'2025-04':'10'},{'2025-04':10,'2025-06':3}])
def test_bad_bounds_rejected(bounds):
    with pytest.raises(ValueError): generate_ids('2025-04',2,'2025-05',1,monthly_end_ids=bounds)


def test_reversed_months_rejected():
    with pytest.raises(ValueError): generate_ids('2026-01',1,'2025-12',2,monthly_end_ids={'2026-01':3})


def test_legacy_range_unchanged():
    ids=generate_ids('2025-04',2523,'2025-04',7522)
    assert len(ids)==5000 and ids[0]=='2504.02523' and ids[-1]=='2504.07522'


def test_multimonth_yaml(tmp_path):
    p=tmp_path/'config.yaml'
    p.write_text("range:\n  start_month: '2025-04'\n  start_id: 8\n  end_month: '2025-05'\n  end_id: 3\n  monthly_end_ids:\n    '2025-04': 10\n")
    config=load_config(p)
    assert len(generate_ids(**config.range))==6

def test_first_month_bound_is_required():
    with pytest.raises(ValueError,match='2025-04'):
        generate_ids('2025-04',8,'2025-05',3)


def test_cross_month_pipeline_resume(tmp_path,monkeypatch):
    import asyncio,httpx
    from crawler.config import CrawlerConfig
    from crawler.pipeline import run_pipeline
    from crawler.progress import ProgressStore
    monkeypatch.chdir(tmp_path)
    config=CrawlerConfig()
    config.range=dict(start_month='2025-12',start_id=2,end_month='2026-01',end_id=2,monthly_end_ids={'2025-12':3})
    expected=['2512.00002','2512.00003','2601.00001','2601.00002']
    calls=[]; clock=[1000.]
    async def sleep(n): clock[0]+=n
    def handler(request):
        calls.append(str(request.url))
        if request.url.path.startswith('/src/'): return httpx.Response(404)
        ids=request.url.params['id_list'].split(',')
        entries=''.join(f'<entry><id>http://arxiv.org/abs/{i if "v" in i else i+"v1"}</id></entry>' for i in ids)
        return httpx.Response(200,content=f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'.encode())
    asyncio.run(run_pipeline(config,{'arxiv'},transport=httpx.MockTransport(handler),now=lambda:clock[0],sleep=sleep))
    store=ProgressStore('runtime')
    assert list(dict.fromkeys(k[0] for k in store.rows))==expected
    assert store.status_counts()['discovery']=={'succeeded':4}
    assert store.status_counts()['metadata']=={'succeeded':4}
    before=len(calls)
    asyncio.run(run_pipeline(config,{'arxiv'},transport=httpx.MockTransport(handler),now=lambda:clock[0],sleep=sleep))
    assert len(calls)==before
