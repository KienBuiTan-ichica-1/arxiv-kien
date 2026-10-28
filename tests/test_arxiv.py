from crawler.arxiv_client import parse_atom

def test_version():
    xml=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2504.02523v3</id><title>T</title></entry></feed>'
    assert parse_atom(xml,'2504.02523')['version']==3

def test_html_is_not_missing():
    import pytest
    with pytest.raises(ValueError): parse_atom(b'<html><body>error</body></html>','2504.02523')

def test_broken_xml_is_payload_error():
    import pytest
    with pytest.raises(ValueError): parse_atom(b'<feed','2504.02523')
