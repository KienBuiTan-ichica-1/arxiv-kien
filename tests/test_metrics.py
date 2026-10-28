from crawler.metrics import weighted_mean, unique_roots
from pathlib import Path

def test_weighted_mean():
    assert weighted_mean([(0,10),(1,30),(4,90)])==25

def test_roots():
    assert unique_roots([Path('runtime'),Path('runtime/temp'),Path('scratch')])==[Path('runtime'),Path('scratch')]

def test_interrupted_session_time_is_not_lost(tmp_path,monkeypatch):
    from crawler.config import CrawlerConfig
    from crawler.metrics import MetricsRecorder
    import crawler.metrics as metrics
    monkeypatch.chdir(tmp_path)
    Path('runtime').mkdir()
    clock=[0.]
    monkeypatch.setattr(metrics.time,'monotonic',lambda:clock[0])
    old=MetricsRecorder(CrawlerConfig()); old.start('old')
    clock[0]=12.; old.sample()
    old.resources.close(); old.log.close()
    new=MetricsRecorder(CrawlerConfig()); new.start('new')
    clock[0]=15.
    summary=new.stop()
    assert summary['active_wall_seconds']>=15
    assert summary['interrupted_run_ids']==['old']
