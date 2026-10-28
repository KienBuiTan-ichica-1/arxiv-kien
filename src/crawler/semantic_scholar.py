import json
import re

FIELDS='title,authors,year,publicationDate,venue,externalIds'

def parse_page(raw,offset):
    page=json.loads(raw)
    if not isinstance(page,dict) or not isinstance(page.get('data'),list): raise ValueError('Missing references data')
    nxt=page.get('next')
    if nxt is not None and (type(nxt) is not int or nxt<=offset): raise ValueError('Non-progressing pagination')
    refs=[]; unresolved=0
    for item in page['data']:
        if not isinstance(item,dict) or 'citedPaper' not in item: raise ValueError('Invalid reference item')
        cited=item.get('citedPaper')
        if cited is None: unresolved+=1; continue
        if not isinstance(cited,dict): raise ValueError('Invalid citedPaper')
        external=cited.get('externalIds') or {}
        if not isinstance(external,dict): raise ValueError('Invalid externalIds')
        authors=cited.get('authors') or []
        if not isinstance(authors,list) or any(not isinstance(a,dict) for a in authors): raise ValueError('Invalid authors')
        arxiv=external.get('ArXiv')
        if arxiv is not None and not isinstance(arxiv,str): raise ValueError('Invalid ArXiv identifier')
        if arxiv: arxiv=re.sub(r'v\d+$','',re.sub(r'^https?://arxiv.org/abs/','',arxiv.strip()))
        refs.append(dict(ref_arxiv_id=arxiv,ref_s2_id=cited.get('paperId'),ref_title=cited.get('title'),ref_authors=[a.get('name') for a in authors],ref_submission_date=cited.get('publicationDate'),year=cited.get('year'),venue=cited.get('venue')))
    return dict(next=nxt,references=refs,unresolved_count=unresolved)
