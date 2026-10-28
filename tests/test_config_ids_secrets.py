import pytest
from crawler.ids import generate_ids
from crawler.config import load_config
from crawler.secrets import load_semantic_scholar_key

def test_range():
    ids=generate_ids('2025-04',2523,'2025-04',7522)
    assert len(ids)==5000
    assert (ids[0],ids[-1])==('2504.02523','2504.07522')

@pytest.mark.parametrize('a,b,c,d',[('2025-04',2,'2025-05',3),('2025-04',4,'2025-04',3)])
def test_invalid(a,b,c,d):
    with pytest.raises(ValueError): generate_ids(a,b,c,d)

def test_config(tmp_path):
    p=tmp_path/'config.yaml'
    p.write_text('paths:\n  persistent_root: /absolute\n')
    with pytest.raises(ValueError): load_config(p)

def test_key(monkeypatch):
    monkeypatch.setenv('SEMANTIC_SCHOLAR_API_KEY',' secret ')
    assert load_semantic_scholar_key()=='secret'
