from flask import Flask,request,send_file,jsonify
from pathlib import Path
from tempfile import TemporaryDirectory
from process_pdfs import extract
from semantic_rank import rank
import zipfile, shutil

app=Flask(__name__)

@app.post('/analyze')
def analyze():
    with TemporaryDirectory() as tmp:
        upload=request.files.getlist('files')
        ip=Path(tmp)/'input';op=Path(tmp)/'out';ip.mkdir()
        for f in upload: f.save(ip/f.filename)
        for pdf in ip.glob("*.pdf"): extract(pdf,op)
        zf=Path(tmp)/'out.zip'
        with zipfile.ZipFile(zf,'w') as z:
            for j in op.glob("*.json"): z.write(j,arcname=j.name)
        return send_file(zf,as_attachment=True)

@app.post('/rank')
def rank_route():
    tmp=TemporaryDirectory()
    cfg=request.files['config']; zipf=request.files['pdfs']
    base=Path(tmp.name); (base/'PDFs').mkdir()
    zipfile.ZipFile(zipf).extractall(base/'PDFs')
    cfg.save(base/'challenge1b_input.json')
    return jsonify(rank(base/'challenge1b_input.json',base))

if __name__=="__main__":
    app.run(host='0.0.0.0',port=8000) 