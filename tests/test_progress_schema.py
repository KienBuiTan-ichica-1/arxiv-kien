import csv
from crawler.progress import ProgressStore
from crawler.storage import atomic_json, digest

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

def test_legacy_jobs_gain_resumable_reference_pass_state(tmp_path):
    path=tmp_path/'progress/jobs.csv'; path.parent.mkdir()
    legacy=['paper','version','stage','offset','status','attempts','total','cycle','error']
    key=('2504.02523',1,'references',0)
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=legacy); writer.writeheader()
        writer.writerow(dict(paper=key[0],version=1,stage='references',offset=0,
            status='running',attempts=3,total=3,cycle=1,error='transport_ReadError'))
    atomic_json(path.with_suffix('.csv.json'),dict(sha256=digest(path),count=1,journal_sequence=0))

    store=ProgressStore(tmp_path)
    assert (store.get(key)['reference_pass'],store.get(key)['batch_cap'])==(1,100)
    store.advance_reference_pass([key],'incomplete_batch_references')

    restored=ProgressStore(tmp_path); row=restored.get(key)
    assert (row['reference_pass'],row['batch_cap'])==(2,100)
    assert (row['status'],row['attempts'],row['total'],row['cycle'])==('pending',0,3,2)
    row['attempts']=3; row['status']='failed'; restored.save()
    restored.reduce_reference_batch([key],'batch_no_response')
    row=ProgressStore(tmp_path).get(key)
    assert (row['reference_pass'],row['batch_cap'],row['attempts'],row['cycle'])==(2,75,0,3)
