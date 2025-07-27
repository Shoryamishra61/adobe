from sentence_transformers import SentenceTransformer,util
import torch, json, fitz, re

model=SentenceTransformer('all-MiniLM-L6-v2',device='cpu')

def embed(txt): return model.encode(txt,convert_to_tensor=True)

def rich_blocks(pdf):
    doc=fitz.open(pdf); blocks=[]
    for pno,p in enumerate(doc,1):
        for b in p.get_text("dict")["blocks"]:
            if b['type']==0:
                t=re.sub(r'\s+',' ',' '.join(s['text'] for l in b['lines'] for s in l['spans']))
                if len(t)>25: blocks.append((t,pno))
    doc.close(); return blocks

def rank(collection_json,base):
    cfg=json.load(open(collection_json,'r',encoding='utf8'))
    query=f"{cfg['persona']['role']} : {cfg['job_to_be_done']['task']}"
    qv=embed(query); corpus=[]; meta=[]
    for d in cfg['documents']:
        for txt,pno in rich_blocks(base/'PDFs'/d['filename']):
            meta.append({"doc":d['filename'],"page":pno,"text":txt[:90]+"..."})
            corpus.append(txt)
    cvs=embed(corpus); scores=util.cos_sim(qv,cvs)[0]
    top=torch.topk(scores,5)
    return [{"document":meta[i]["doc"],"page":meta[i]["page"],
             "section_title":meta[i]["text"],"importance_rank":r+1}
            for r,i in enumerate(top.indices)] 