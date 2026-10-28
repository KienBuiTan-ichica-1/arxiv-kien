import csv
from crawler.progress import ProgressStore

def test_two_schemas_and_page_count(tmp_path):
    store=ProgressStore(tmp_path); store.initialize(['2504.02523'])
    store.add(('2504.02523',0,'references',100)); store.save()
    assert store.status_counts()['references']['pending']==1
    papers=list(csv.DictReader((tmp_path/'progress/papers.csv').open()))
    assert len(papers)==1
    assert 'references_page_cycle_attempts' in papers[0]
    assert (tmp_path/'progress/versions.csv').exists()

def test_page_budget_survives_reload(tmp_path):
    store=ProgressStore(tmp_path); store.initialize(['2504.02523'])
    key=('2504.02523',0,'references',100)
    store.add(key); store.start_attempt(key)
    restored=ProgressStore(tmp_path)
    assert restored.get(key)['attempts']==1
    assert restored.status_counts()['references']['running']==1
