import pytest
from crawler.semantic_scholar import parse_page

def test_null():
    assert parse_page(b'{"data":[{"citedPaper":null}]}',0)['unresolved_count']==1

def test_loop():
    with pytest.raises(ValueError): parse_page(b'{"data":[],"next":0}',0)

@pytest.mark.parametrize('raw',[b'{"data":[42]}',b'{"data":[{}]}',b'{"data":[{"citedPaper":42}]}'])
def test_malformed_item(raw):
    with pytest.raises(ValueError): parse_page(raw,0)
