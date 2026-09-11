"""Local SQLite, immutable completed snapshots on a private HF bucket mount.

Never run SQLite WAL on object storage. A successful write response is released
only after a verified snapshot and all referenced audio have been written.
"""
import hashlib,json,os,re,shutil,sqlite3,time,uuid
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def write_closed(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'xb') as f:
        f.write(data);f.flush()
        try:os.fsync(f.fileno())
        except OSError as e:
            if e.errno not in (22,95,38):raise
    if path.read_bytes()!=data:raise RuntimeError('Persistent storage read-back failed')

class Store:
    def __init__(self,local,durable):
        self.local=Path(local);self.durable=Path(durable)
        self.local.mkdir(parents=True,exist_ok=True)
        self.durable.mkdir(parents=True,exist_ok=True)
        self.snapshots=self.durable/'snapshots';self.snapshots.mkdir(exist_ok=True)
        self.last=None
    def restore(self):
        markers=sorted(self.snapshots.glob('*.json'),reverse=True)
        if not markers:return False
        # Fail closed on a corrupt latest completed snapshot; do not silently
        # resurrect an older participant state or lose acknowledged responses.
        m=json.loads(markers[0].read_text());source=self.snapshots/m['database']
        if Path(m['database']).name!=m['database'] or sha(source)!=m['sha256']:raise RuntimeError('Invalid latest persistent database snapshot')
        shutil.copyfile(source,self.local/'study.sqlite')
        for a in m['audio']:
            key=a['object_key']
            if not re.fullmatch(r'interactive/X-[A-F0-9]{32}/[0-9]+-[a-f0-9]{64}\.wav',key):raise RuntimeError('Invalid audio path')
            src=self.durable/'audio'/key;dst=self.local/'audio'/key
            if sha(src)!=a['sha256']:raise RuntimeError('Persistent audio verification failed')
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        self.last=markers[0].name;return True
    def checkpoint(self):
        tmp=self.local/('backup-'+uuid.uuid4().hex+'.sqlite')
        source=sqlite3.connect('file:'+str(self.local/'study.sqlite')+'?mode=ro',uri=True)
        dest=sqlite3.connect(tmp)
        try:
            source.backup(dest)
            if dest.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('Database verification failed')
            rows=[{'object_key':r[0],'sha256':r[1]} for r in dest.execute('SELECT object_key,sha256 FROM interactive_audio')]
        finally:dest.close();source.close()
        try:
            for a in rows:
                src=self.local/'audio'/a['object_key'];dst=self.durable/'audio'/a['object_key']
                if sha(src)!=a['sha256']:raise RuntimeError('Local audio verification failed')
                if not dst.exists():write_closed(dst,src.read_bytes())
                if sha(dst)!=a['sha256']:raise RuntimeError('Persistent audio verification failed')
            stamp=f'{time.time_ns():020d}-{uuid.uuid4().hex}'
            dbname=stamp+'.sqlite';digest=sha(tmp)
            write_closed(self.snapshots/dbname,tmp.read_bytes())
            if sha(self.snapshots/dbname)!=digest:raise RuntimeError('Persistent snapshot verification failed')
            manifest={'version':1,'database':dbname,'sha256':digest,'audio':rows,'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
            write_closed(self.snapshots/(stamp+'.json'),json.dumps(manifest).encode())
            self.last=stamp+'.json'
            return manifest
        finally:tmp.unlink(missing_ok=True)
