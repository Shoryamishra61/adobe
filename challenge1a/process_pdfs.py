import fitz, pdfplumber, pandas as pd, re, json, statistics
from pathlib import Path

def base_font(doc):
    sizes=[round(s['size']) for p in doc for b in p.get_text("dict")["blocks"]
           if b['type']==0 for l in b['lines'] for s in l['spans'] if s['text'].strip()]
    return statistics.mode(sizes) if sizes else 12

def tables(path):
    out=[]
    with pdfplumber.open(path) as pdf:
        for pno,p in enumerate(pdf.pages,1):
            for i,t in enumerate(p.extract_tables()):
                df=pd.DataFrame(t[1:],columns=t[0])
                out.append({"page":pno,"idx":i+1,"data":df.to_dict('records')})
    return out

def outline(doc,bsize):
    heads=[]
    for pno,p in enumerate(doc,1):
        for blk in p.get_text("dict")["blocks"]:
            if blk["type"]==0 and blk['lines']:
                ln=blk['lines'][0]; span=ln['spans'][0]
                txt=re.sub(r'\s+',' ', " ".join(s['text'] for s in ln['spans'])).strip()
                fs,b='size','bold'; fs=span[fs]; b='bold' in span['font'].lower()
                lev=None
                if len(txt)<150 and b:
                    lev="H1" if fs>bsize*1.6 else "H2" if fs>bsize*1.3 else "H3" if fs>bsize*1.1 else None
                if lev: heads.append({"level":lev,"text":txt,"page":pno})
    return heads

def extract(pdf_path,out_dir):
    doc=fitz.open(pdf_path); b=base_font(doc)
    result={"title":doc.metadata.get('title',pdf_path.stem),
            "outline":outline(doc,b),"tables":tables(pdf_path)}
    (out_dir/f"{pdf_path.stem}.json").write_text(json.dumps(result,indent=2,ensure_ascii=False))
    doc.close()