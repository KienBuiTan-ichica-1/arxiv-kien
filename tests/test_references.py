import pytest
from crawler.semantic_scholar import parse_batch, parse_page

def test_null():
    assert parse_page(b'{"data":[{"citedPaper":null}]}',0)['unresolved_count']==1

def test_loop():
    with pytest.raises(ValueError): parse_page(b'{"data":[],"next":0}',0)

@pytest.mark.parametrize('raw',[b'{"data":[42]}',b'{"data":[{}]}',b'{"data":[{"citedPaper":42}]}'])
def test_malformed_item(raw):
    with pytest.raises(ValueError): parse_page(raw,0)

def test_batch_classifies_complete_null_and_count_mismatch_per_version():
    raw=b'''[
      {"paperId":"S2-main","referenceCount":1,"references":[
        {"paperId":"S2-ref","title":"Reference","authors":[{"name":"Ada"}],
         "year":2025,"publicationDate":"2025-01-02","venue":"Venue",
         "externalIds":{"ArXiv":"2501.00001v2"}}]},
      null,
      {"paperId":"S2-short","referenceCount":2,"references":[
        {"paperId":"S2-only","title":"Only","authors":[],"externalIds":{}}]}
    ]'''
    results=parse_batch(raw,['URL:v1','URL:v2','URL:v3'])
    assert results[0]['complete'] is True
    assert results[0]['references']==[dict(ref_arxiv_id='2501.00001',ref_s2_id='S2-ref',
        ref_title='Reference',ref_authors=['Ada'],ref_submission_date='2025-01-02',year=2025,venue='Venue')]
    assert [(r['complete'],r['error']) for r in results[1:]]==[
        (False,'paper_not_found'),(False,'reference_count_mismatch')]
