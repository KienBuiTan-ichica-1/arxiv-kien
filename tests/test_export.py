from crawler.config import CrawlerConfig
from crawler.progress import ProgressStore
from crawler.export import export_snapshot
import pyarrow.parquet as pq

def test_missing_metadata_retains_id(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    c=CrawlerConfig(); c.range['end_id']=2523
    ProgressStore('runtime').initialize(['2504.02523'])
    manifest=export_snapshot(c,'test-run')
    table=pq.read_table('runtime/exports/test-run/papers.parquet')
    assert table.to_pylist()[0]['arxiv_id']=='2504.02523'
    assert table.to_pylist()[0]['title'] is None
    assert manifest['papers']==1
