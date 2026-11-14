"""Anonymous scholarly discovery and conservative venue verification."""
import asyncio
import json
import re
import unicodedata
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
from defusedxml import ElementTree as ET
from .network import fetch
from .domains import all_domains,match_domains
from .config import get_settings
from .db import connect
from .ingest import ingest_pdf,update_job,resolve

VENUES=('ICML','ICLR','CVPR','ACL','EMNLP','NeurIPS')
NS={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom'}

def normalized(title):return re.sub(r'[^\w]','',unicodedata.normalize('NFKC',title)).casefold()

def venue_from_text(text,allow_workshop=False):
    if re.search(r'submitted to|under review|under submission|preprint|rejected|withdrawn',text,re.I):return None
    if not allow_workshop and re.search(r'workshop|findings|demo(?:nstration)?|student research',text,re.I):return None
    m=re.search(r'\b(ICML|ICLR|CVPR|ACL|EMNLP|NeurIPS|NIPS)\b[^\d]{0,15}(20\d{2})',text,re.I)
    if not m:
        m2=re.search(r'(20\d{2})[^\w]{0,10}\b(ICML|ICLR|CVPR|ACL|EMNLP|NeurIPS)\b',text,re.I)
        if not m2:return None
        venue,year=m2[2],m2[1]
    else:venue,year=m[1],m[2]
    venue='NeurIPS' if venue.lower() in ('nips','neurips') else venue.upper()
    tier='oral' if re.search(r'\boral\b',text,re.I) else 'spotlight' if re.search(r'\bspotlight\b',text,re.I) else 'poster'
    return {'venue':venue,'venue_year':int(year),'venue_tier':tier}

def parse_arxiv(data):
    root=ET.fromstring(data);papers=[]
    for e in root.findall('a:entry',NS):
        aid=e.findtext('a:id','',NS).split('/abs/')[-1]
        if not re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?',aid):continue
        title=' '.join(e.findtext('a:title','',NS).split())
        paper={'arxiv_id':aid,'doc_uid':aid,'title':title,'abstract':e.findtext('a:summary','',NS).strip(),'authors':[a.findtext('a:name','',NS) for a in e.findall('a:author',NS)],'source_type':'arxiv','published':e.findtext('a:published','',NS),'source_urls':{'pdf':f'https://arxiv.org/pdf/{aid}','html':f'https://arxiv.org/html/{aid}'}}
        v=venue_from_text(e.findtext('x:comment','',NS)+' '+e.findtext('x:journal_ref','',NS))
        if v:paper.update(v)
        papers.append(paper)
    return papers

async def arxiv_search(domain,days=3,years=None,max_results=80):
    phrases=domain.get('phrases',[])[:10]
    terms=' OR '.join('all:"'+p.replace('"','')+'"' for p in phrases)
    cats=' OR '.join('cat:'+c for c in domain.get('arxiv_cats',['cs.AI','cs.CL','cs.LG']))
    if years:
        start=f'{min(years)}01010000';end=f'{max(years)}12312359'
    else:
        start=(datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y%m%d0000');end=datetime.now(timezone.utc).strftime('%Y%m%d2359')
    query=f'({terms}) AND ({cats}) AND submittedDate:[{start} TO {end}]'
    return parse_arxiv(await fetch('https://export.arxiv.org/api/query?'+urlencode({'search_query':query,'max_results':max_results,'sortBy':'submittedDate','sortOrder':'descending'}),6*1024**2))

async def hf_daily(days=3):
    papers={}
    for n in range(min(days,14)):
        date=(datetime.now(timezone.utc)-timedelta(days=n)).strftime('%Y-%m-%d')
        data=json.loads(await fetch('https://huggingface.co/api/daily_papers?'+urlencode({'date':date,'limit':50}),5*1024**2))
        for entry in data:
            p=entry.get('paper',entry);aid=p.get('id','')
            if not re.fullmatch(r'\d{4}\.\d{4,5}',aid):continue
            papers[aid]={'arxiv_id':aid,'doc_uid':aid,'title':p.get('title',''),'abstract':p.get('summary',''),'authors':[a.get('name','') for a in p.get('authors',[])],'hf_upvotes':p.get('upvotes',entry.get('upvotes',0)),'source_type':'hf','keywords':' '.join(p.get('ai_keywords',[])),'source_urls':{'pdf':f'https://arxiv.org/pdf/{aid}','html':f'https://arxiv.org/html/{aid}','hf':f'https://huggingface.co/papers/{aid}'}}
    return list(papers.values())

def content_value(content,key,default=''):
    v=content.get(key,default)
    return v.get('value',default) if isinstance(v,dict) else v

async def verify_openreview(title):
    data=json.loads(await fetch('https://api2.openreview.net/notes?'+urlencode({'content.title':title,'limit':10}),3*1024**2))
    for note in data.get('notes',[]):
        c=note.get('content',{})
        if normalized(content_value(c,'title'))!=normalized(title):continue
        vid=content_value(c,'venueid');venue=content_value(c,'venue')
        # Accepted venueid is the conference root, not /Submission, /Rejected or a workshop.
        m=re.fullmatch(r'(ICLR\.cc|ICML\.cc|NeurIPS\.cc)/(20\d{2})/Conference',vid)
        if not m:continue
        v=venue_from_text(venue) or {'venue':m[1].split('.')[0],'venue_year':int(m[2]),'venue_tier':'poster'}
        v['openreview']='https://openreview.net/forum?id='+note['id'];return v
    return None

async def verify_dblp(title):
    data=json.loads(await fetch('https://dblp.org/search/publ/api?'+urlencode({'q':title,'format':'json','h':5}),3*1024**2))
    hits=data.get('result',{}).get('hits',{}).get('hit',[])
    if isinstance(hits,dict):hits=[hits]
    for hit in hits:
        info=hit['info']
        if normalized(info.get('title',''))!=normalized(title):continue
        key=info.get('key','')
        if not re.match(r'conf/(?:icml|iclr|cvpr|acl|emnlp|nips)/',key):continue
        venue=info.get('venue','')
        if isinstance(venue,list):venue=' '.join(venue)
        v=venue_from_text(venue+' '+str(info.get('year','')))
        if v:return v
    return None

async def verified(paper):
    if paper.get('venue') in VENUES:return paper
    for verifier in (verify_openreview,verify_dblp):
        try:v=await verifier(paper['title'])
        except Exception:continue
        if v:
            or_url=v.pop('openreview',None)
            paper.update(v)
            if or_url:paper.setdefault('source_urls',{})['openreview']=or_url
            return paper
    return paper if paper.get('hf_upvotes',0)>=get_settings().hf_min_upvotes else None

async def openalex_growth(title):
    try:
        data=json.loads(await fetch('https://api.openalex.org/works?'+urlencode({'search':title,'per-page':3}),2*1024**2))
        for w in data.get('results',[]):
            if normalized(w['title'])==normalized(title):
                year=datetime.now(timezone.utc).year
                return sum(c['cited_by_count'] for c in w.get('counts_by_year',[]) if c['year']>=year-1)
    except Exception:pass
    return 0

async def sync(source='all',days=3,backfill=False,years=(2025,2026),domain='all',limit=50,job_id=None,user_id=None,vision_driver=None):
    configs=[d for d in all_domains() if domain=='all' or d['slug'] in domain.split(',')]
    if not configs:raise ValueError('没有匹配的激活领域')
    candidates=[];errors=[]
    update_job(job_id,2,'正在召回候选论文')
    if source in ('all','hf') and not backfill:
        try:candidates.extend(await hf_daily(days))
        except Exception:errors.append('HF Daily 暂时不可用')
    if source in ('all','arxiv'):
        for d in configs:
            try:candidates.extend(await arxiv_search(d,days,years if backfill else None,max(50,limit*3)))
            except Exception:errors.append(d['slug']+' arXiv 暂时不可用')
    dedup={p['doc_uid']:p for p in candidates}
    eligible=[]
    for i,p in enumerate(dedup.values()):
        domains=match_domains(p['title']+' '+p.get('abstract','')+' '+p.get('keywords',''),configs)
        if not domains:continue
        with connect() as db:
            if db.execute('SELECT id FROM papers WHERE doc_uid=?',(p['doc_uid'],)).fetchone():continue
        update_job(job_id,5+int(25*i/max(1,len(dedup))),f'正在核验顶会录用 · {i+1}/{len(dedup)}')
        p=await verified(p)
        if not p:continue
        if backfill and p.get('venue_year') not in years:continue
        p['domains']=domains
        p['citation_growth']=await openalex_growth(p['title']) if backfill else 0
        eligible.append(p)
    eligible.sort(key=lambda p:({'oral':3,'spotlight':2,'poster':1}.get(p.get('venue_tier'),0),p.get('hf_upvotes',0),p.get('citation_growth',0)),reverse=True)
    chosen=[];counts={d['slug']:0 for d in configs}
    for p in eligible:
        if not any(counts[d]<limit for d in p['domains']):continue
        chosen.append(p)
        for d in p['domains']:counts[d]+=1
    completed=0;failed=0
    for i,p in enumerate(chosen):
        update_job(job_id,30+int(65*i/max(1,len(chosen))),f'正在入库 {i+1}/{len(chosen)} · {p["title"][:80]}')
        try:
            data=await fetch(p['source_urls']['pdf'])
            await ingest_pdf(data,p,user_id,vision_driver=vision_driver);completed+=1
        except Exception:failed+=1
    status='failed' if not candidates and errors else 'completed'
    update_job(job_id,100,f'入库 {completed} 篇，失败 {failed} 篇'+('；'+'；'.join(errors) if errors else ''),status)
    return {'completed':completed,'failed':failed,'source_errors':errors}
