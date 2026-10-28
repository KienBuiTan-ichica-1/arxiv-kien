import pytest
from crawler.sources import inspect_and_extract
from crawler.config import CrawlerConfig

def test_html(tmp_path):
    archive=tmp_path/'download'; archive.write_bytes(b'<html>Oops</html>')
    with pytest.raises(ValueError): inspect_and_extract(archive,tmp_path/'out',CrawlerConfig())

def test_tex(tmp_path):
    archive=tmp_path/'download'; raw=b'\\documentclass{article}\n\\includegraphics{image}'
    archive.write_bytes(raw)
    result=inspect_and_extract(archive,tmp_path/'out',CrawlerConfig())
    assert result['status']=='succeeded'
    assert (tmp_path/'out'/'tex'/'source.tex').read_bytes()==raw

def test_corrupt_gzip(tmp_path):
    archive=tmp_path/'bad'; archive.write_bytes(b'\x1f\x8b\x08\x00'+b'\x00'*6+b'\xff'*20)
    with pytest.raises(ValueError): inspect_and_extract(archive,tmp_path/'out',CrawlerConfig())
