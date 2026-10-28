from crawler.progress import ProgressStore

def test_recovery(tmp_path):
    s=ProgressStore(tmp_path)
    s.initialize(['2504.02523'])
    key=('2504.02523',0,'discovery',0)
    for _ in range(3): s.start_attempt(key)
    s=ProgressStore(tmp_path)
    assert s.get(key)['attempts']==3
    assert not s.pending('discovery')

def test_preserve_valid_backup(tmp_path):
    s=ProgressStore(tmp_path); s.initialize(['2504.02523']); s.save()
    s.path.write_text('corrupt')
    recovered=ProgressStore(tmp_path); recovered.save()
    recovered.path.write_text('another corruption')
    assert len(ProgressStore(tmp_path).rows)==2
