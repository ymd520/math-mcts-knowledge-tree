import gzip,pathlib,shutil,tempfile,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
def ensure_database():
    p=ROOT/'data/knowledge.sqlite'
    if p.exists():return p
    z=p.with_suffix('.sqlite.gz')
    if not z.exists():raise FileNotFoundError('Missing knowledge database. Run python src/build.py')
    fd,tmp=tempfile.mkstemp(dir=p.parent,suffix='.sqlite.tmp');os.close(fd)
    try:
        with gzip.open(z,'rb') as a,open(tmp,'wb') as b:shutil.copyfileobj(a,b)
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return p
