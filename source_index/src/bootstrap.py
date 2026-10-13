"""Download or reuse a pinned Apache-2.0 source snapshot, verify it, then index."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys,tempfile,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
COMMIT='105b9b1ce126e77b467aac6f6ba36b510ac57368'
EXPECTED='b9043ecf0ec44b5df9f53704e6edef0a2e6b46ecd431a4299786d6e9fb393ec1'
URL='https://codeload.github.com/leanprover-community/mathlib4/tar.gz/'+COMMIT

def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(1<<20):h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=pathlib.Path);p.add_argument('--no-build',action='store_true');a=p.parse_args()
    for d in ['data','vendor','reports']:(ROOT/d).mkdir(exist_ok=True)
    target=ROOT/'vendor/mathlib4.tar.gz'
    if target.exists():
        if sha256(target)!=EXPECTED:raise SystemExit('Existing archive SHA-256 mismatch. Refusing to index.')
    else:
        with tempfile.TemporaryDirectory(dir=ROOT/'vendor') as tmp:
            staging=pathlib.Path(tmp)/'snapshot.tar.gz'
            if a.archive:
                if sha256(a.archive)!=EXPECTED:raise SystemExit('Provided archive SHA-256 mismatch.')
                shutil.copyfile(a.archive,staging)
            else:
                print('Downloading pinned mathlib4 snapshot:',COMMIT)
                with urllib.request.urlopen(URL,timeout=60) as response,staging.open('wb') as out:shutil.copyfileobj(response,out)
            actual=sha256(staging)
            if actual!=EXPECTED:raise SystemExit('Downloaded archive SHA-256 mismatch: '+actual+'; refusing to index.')
            staging.replace(target)
    print('Verified source archive:',COMMIT,EXPECTED)
    if not a.no_build:
        subprocess.run([sys.executable,str(ROOT/'src/build.py')],check=True)
        subprocess.run([sys.executable,str(ROOT/'src/validate.py')],check=True)
if __name__=='__main__':main()
