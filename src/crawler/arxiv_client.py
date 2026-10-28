import re
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

NS={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}

def parse_atom(raw,paper,version=None):
    try: 
        root=ElementTree.fromstring(raw)
    except (ParseError,DefusedXmlException) as exc: 
        raise ValueError('Invalid Atom XML') from exc
    if root.tag != '{http://www.w3.org/2005/Atom}feed': 
        raise ValueError('Expected Atom feed')
    entries = root.findall('a:entry',NS)
    if not entries:
        return {'not_found':True}
    if len(entries) != 1:
        raise ValueError('Unexpected Atom entry count')
    entry = entries[0]
    def text(name): 
        return entry.findtext(name,default=None,namespaces=NS)
    identifier = text('a:id') or ''
    match = re.search(r'/abs/(.+)v([1-9][0-9]*)$',identifier)
    if not match or match[1] != paper or (version and int(match[2]) != version):
        raise ValueError('Atom ID mismatch or error entry')
    return dict(arxiv_id=paper, version=int(match[2]), 
                title=text('a:title'), abstract=text('a:summary'), 
                authors=[a.findtext('a:name', namespaces = NS) 
                         for a in entry.findall('a:author',NS)] , 
                categories=[a.get('term') for a in entry.findall('a:category', NS)],
                published=text('a:published'),updated=text('a:updated'),
                journal_ref=text('x:journal_ref'), doi=text('x:doi'), venue=None)

def parse_atom_batch(raw, requested_papers):
  """Parse Atom XML chứa nhiều entry cho một danh sách ID."""
  try:
    root = ElementTree.fromstring(raw)
  except (ParseError, DefusedXmlException) as exc:
    raise ValueError("Invalid Atom XML") from exc
  if root.tag != "{http://www.w3.org/2005/Atom}feed":
    raise ValueError("Expected Atom feed")

  entries = root.findall("a:entry", NS)
  results = {}

  for entry in entries:

    def text(name):
      return entry.findtext(name, default=None, namespaces=NS)

    identifier = text("a:id") or ""
    # Trích xuất arxiv_id và version từ id URL, ví dụ: http://arxiv.org/abs/2504.02523v2
    match = re.search(r"/abs/(.+)v([1-9][0-9]*)$", identifier)
    if not match:
      continue
    paper = match[1]
    version = int(match[2])
    results[paper] = dict(
        arxiv_id=paper,
        version=version,
        title=text("a:title"),
        abstract=text("a:summary"),
        authors=[
            a.findtext("a:name", namespaces=NS)
            for a in entry.findall("a:author", NS)
        ],
        categories=[a.get("term") for a in entry.findall("a:category", NS)],
        published=text("a:published"),
        updated=text("a:updated"),
        journal_ref=text("x:journal_ref"),
        doi=text("x:doi"),
        venue=None,
    )

  # Những bài arXiv không tìm thấy thì đánh dấu not_found
  for p in requested_papers:
    if p not in results:
      results[p] = {"not_found": True, "arxiv_id": p}

  return results