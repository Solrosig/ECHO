"""Prepare a self-contained upload folder for the recipient's own Space."""
from pathlib import Path
import shutil,zipfile,json
here=Path(__file__).resolve().parent
root=here.parents[1]
out=root/'space-upload'
if out.exists():raise SystemExit('space-upload already exists. Move it aside before creating a new release.')
out.mkdir()
for name in ['app.py','web_host.py','persistent_store.py','requirements.txt','packages.txt','README.md','backend.zip']:
    shutil.copy2(here/name,out/name)
include=['server','drizzle','db','public','dist','vendor']
files=[p for p in root.iterdir() if p.is_file() and p.suffix in ['.js','.mjs','.html','.css','.json','.yaml','.ts']]
files=[p for p in files if p.name not in ['release-manifest.json']]
for name in include:
    files.extend(p for p in (root/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
with zipfile.ZipFile(out/'webapp.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(set(files)):
        if p.name=='downloads.json':continue
        z.write(p,p.relative_to(root).as_posix())
    # Browser models are already bundled; no author's model host is needed.
    z.writestr('downloads.json','[]\n')
print('Upload the contents of '+str(out)+' to your own Space. Mount a PRIVATE bucket at /data first.')
