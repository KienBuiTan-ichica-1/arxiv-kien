import json
import re

FIELDS='title,authors,year,publicationDate,venue,externalIds'

def normalize_reference(cited):
    if not isinstance(cited,dict): raise ValueError('Invalid citedPaper')
    external=cited.get('externalIds') or {}
    if not isinstance(external,dict): raise ValueError('Invalid externalIds')
    authors=cited.get('authors') or []
    if not isinstance(authors,list) or any(not isinstance(a,dict) for a in authors): raise ValueError('Invalid authors')
    arxiv=external.get('ArXiv')
    if arxiv is not None and not isinstance(arxiv,str): raise ValueError('Invalid ArXiv identifier')
    if arxiv: arxiv=re.sub(r'v\d+$','',re.sub(r'^https?://arxiv.org/abs/','',arxiv.strip()))
    return dict(ref_arxiv_id=arxiv,ref_s2_id=cited.get('paperId'),ref_title=cited.get('title'),
                ref_authors=[a.get('name') for a in authors],ref_submission_date=cited.get('publicationDate'),
                year=cited.get('year'),venue=cited.get('venue'))

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
        refs.append(normalize_reference(cited))
    return dict(next=nxt,references=refs,unresolved_count=unresolved)

def parse_batch(raw,requested):
    payload=json.loads(raw)
    if not isinstance(payload,list) or len(payload)!=len(requested):
        raise ValueError('Batch response does not match request')
    results=[]
    for identifier,item in zip(requested,payload):
        result=dict(requested_identifier=identifier,returned_paper_id=None,
                    reference_count=None,references=[],complete=False,error='')
        if item is None:
            result['error']='paper_not_found'; results.append(result); continue
        if not isinstance(item,dict):
            result['error']='invalid_paper'; results.append(result); continue
        result['returned_paper_id']=item.get('paperId')
        count=item.get('referenceCount'); references=item.get('references')
        if type(count) is not int or count<0 or not isinstance(references,list):
            result['error']='invalid_reference_count'; results.append(result); continue
        result['reference_count']=count
        try: result['references']=[normalize_reference(reference) for reference in references]
        except ValueError:
            result['error']='invalid_reference_item'; results.append(result); continue
        if len(references)!=count:
            result['error']='reference_count_mismatch'; results.append(result); continue
        result['complete']=True; results.append(result)
    return results
