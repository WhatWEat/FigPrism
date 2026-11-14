"""Bounded in-memory TeX source inspection: never execute TeX, extract paths, or follow links."""
import gzip
import io
import posixpath
import re
import tarfile
import fitz
from .extraction import Crop, detect

MAX_UNPACKED=120*1024**2

def unpack(data):
    files={};total=0
    try:
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as tar:
            for n,m in enumerate(tar):
                if n>4000: raise ValueError('Too many source files')
                name=posixpath.normpath(m.name)
                if not m.isfile() or name.startswith(('../','/')): continue
                if m.size>30*1024**2: continue
                total+=m.size
                if total>MAX_UNPACKED: raise ValueError('Source archive too large')
                if name.lower().endswith(('.tex','.pdf','.png','.jpg','.jpeg','.eps')):
                    f=tar.extractfile(m)
                    if f: files[name]=f.read()
    except tarfile.ReadError:
        raw=gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data
        if len(raw)>MAX_UNPACKED: raise ValueError('Source too large')
        files['main.tex']=raw
    return files

def expand(files,name,seen=None):
    seen=set() if seen is None else seen
    if name in seen or len(seen)>100: return ''
    seen.add(name)
    text=files.get(name,b'').decode('utf-8','replace')
    text=re.sub(r'(?<!\\)%[^\n]*','',text)
    def include(m):
        target=posixpath.normpath(posixpath.join(posixpath.dirname(name),m[1]))
        if not target.endswith('.tex'): target+='.tex'
        return expand(files,target,seen)
    return re.sub(r'\\(?:input|include)\s*\{([^}]+)\}',include,text)

def balanced(text,start):
    depth=0
    for i in range(start,len(text)):
        if text[i]=='{' and (i==0 or text[i-1]!='\\'): depth+=1
        if text[i]=='}' and (i==0 or text[i-1]!='\\'):
            depth-=1
            if depth==0: return text[start+1:i]
    return ''

def clean(text):
    text=re.sub(r'\\(?:label|cite\w*)\{[^}]*\}','',text)
    text=re.sub(r'\\[a-zA-Z]+\*?(?:\[[^]]*\])?','',text)
    return re.sub(r'\s+',' ',text.replace('{','').replace('}','')).strip()

def figures(files):
    mains=[n for n,b in files.items() if n.endswith('.tex') and b'\\documentclass' in b]
    if not mains: return []
    main=min(mains,key=len);text=expand(files,main);results=[]
    for i,m in enumerate(re.finditer(r'\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}',text,re.S),1):
        body=m[1];cap=re.search(r'\\caption(?:\[[^]]*\])?\s*\{',body)
        caption=clean(balanced(body,cap.end()-1)) if cap else ''
        graphics=re.findall(r'\\includegraphics\*?(?:\s*\[[^]]*\])?\s*\{([^}]+)\}',body)
        tikz=re.search(r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}',body,re.S)
        assets=[]
        for g in graphics:
            matches=[n for n in files if n==g or n.rsplit('.',1)[0]==g or n.endswith('/'+g) or n.rsplit('.',1)[0].endswith('/'+g)]
            if matches:
                name=min(matches,key=len);raw=files[name]
                try:
                    if name.lower().endswith(('.png','.jpg','.jpeg')):
                        d=fitz.open(stream=raw);raw=d.convert_to_pdf();d.close()
                    if raw.startswith(b'%PDF'): assets.append(raw)
                except Exception: pass
        complex_composition=bool(re.search(r'\\(?:subfigure|subfloat|put|overpic)|\\begin\{(?:subfigure|overpic|tikzpicture)\}',body))
        results.append({'label':f'Fig. {i}','caption':caption,'raw':assets[0] if len(assets)==1 and len(graphics)==1 and not complex_composition else None,'subassets':assets if len(assets)>1 else [],'tikz':tikz[0] if tikz else None})
    return results

def merge_crops(doc,source_figures):
    crops=[]
    for page in doc: crops.extend(detect(page))
    for source in source_figures:
        crop=next((c for c in crops if c.label==source['label']),None)
        if crop:
            crop.raw=source['raw'];crop.tikz=source['tikz']
            if crop.raw: crop.confidence=.96
            if source['caption']: crop.caption=source['caption']
        elif source['raw']:
            # Source-native figure remains usable even when PDF geometry could not find it.
            page_num=1
            for page in doc:
                if re.search(r'Figure\s+'+re.escape(source['label'].split()[-1])+r'\b',page.get_text()): page_num=page.number+1;break
            crop=Crop(page_num,list(doc[page_num-1].rect),source['label'],source['caption'],.9,raw=source['raw'],tikz=source['tikz'])
            crops.append(crop)
        if crop and source['subassets']:
            # Match source panels in the composite; no guessed asset-to-region association.
            try:
                import cv2
                import numpy as np
                page=doc[crop.page-1];rect=fitz.Rect(crop.bbox)
                pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),clip=rect)
                target=cv2.cvtColor(np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,pix.n)[:,:,:3],cv2.COLOR_RGB2GRAY)
                subs=[]
                for i,raw in enumerate(source['subassets']):
                    d=fitz.open(stream=raw,filetype='pdf');p=d[0].get_pixmap();template=cv2.cvtColor(np.frombuffer(p.samples,np.uint8).reshape(p.height,p.width,p.n)[:,:,:3],cv2.COLOR_RGB2GRAY)
                    best=None
                    for scale in np.linspace(.4,2,18):
                        t=cv2.resize(template,None,fx=scale,fy=scale)
                        if t.shape[0]>=target.shape[0] or t.shape[1]>=target.shape[1]:continue
                        _,score,_,point=cv2.minMaxLoc(cv2.matchTemplate(target,t,cv2.TM_CCOEFF_NORMED))
                        if best is None or score>best[0]:best=(score,point,t.shape)
                    if best and best[0]>.65:
                        _,(x,y),(h,w)=best;label=chr(97+i)
                        subs.append({'id':label,'label':f'({label})','caption':'','norm_bbox':[x/pix.width,y/pix.height,(x+w)/pix.width,(y+h)/pix.height],'raw':raw})
                    d.close()
                crop.subitems=subs
            except ImportError:pass
    return crops
