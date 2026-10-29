import pytest
from types import SimpleNamespace
from crawler.progress import ProgressStore
from crawler.verification import audit

def fixture(tmp_path):
    store=ProgressStore(tmp_path); store.initialize(['2504.00001'])
    key=('2504.00001',0,'discovery',0)
    staging=tmp_path/'staging'; staging.mkdir()
    (staging/'normalized.json').write_text('{"version":0}')
    store.storage.commit(key,staging); store.finish(key,'succeeded')
    return store,key,SimpleNamespace(paths={'persistent_root':str(tmp_path)})

def test_receipt_skip_and_manifest_change(tmp_path):
    store,key,config=fixture(tmp_path)
    assert audit(config)['skipped']==1
    marker=store.storage.result_dir(key)/'complete.json'
    marker.write_text(marker.read_text()+' ')
    assert not store.storage.is_verified(key)
    assert audit(config)['verified']==1

def test_audit_resume_after_interrupt(tmp_path):
    store,key,config=fixture(tmp_path)
    (store.storage.result_dir(key)/'verification.json').unlink()
    def stop(_): raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt): audit(config,report=stop)
    assert audit(config)['skipped']==1

def test_resume_does_not_hash_success(tmp_path,monkeypatch):
    store,key,config=fixture(tmp_path)
    def forbidden(_): raise AssertionError('hashed successful result')
    monkeypatch.setattr(store.storage,'verify',forbidden)
    store.reconcile(recovery_only=True)

def test_corrupt_payload_not_certified(tmp_path):
    store,key,config=fixture(tmp_path)
    target=store.storage.result_dir(key)
    (target/'verification.json').unlink()
    (target/'normalized.json').write_text('broken')
    assert audit(config)['invalid']==1
    assert not store.storage.is_verified(key)

def test_full_audit_resumes_and_new_full_rechecks(tmp_path):
    store,key,config=fixture(tmp_path)
    def stop(_): raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt): audit(config,full=True,report=stop)
    assert audit(config,full=True)['skipped']==1
    assert audit(config,full=True)['verified']==1

def test_interrupted_job_recovers_published_result(tmp_path):
    store,key,config=fixture(tmp_path)
    store.rows[key].update(status='running',attempts=1)
    store.reconcile(recovery_only=True,ids={key[0]},stages={'discovery'})
    assert store.rows[key]['status']=='succeeded'
