"""Prepare a self-contained upload folder for the ECHO Hugging Face Space.

backend.zip is rebuilt from ../../tts-service, the reviewed code. The RAVDESS reference WAVs are not in git, so they
are copied from an earlier backend.zip: keep the release's backend.zip beside this script or pass --refs-from.
Run pnpm build first, because the website is packaged from dist.
"""
import argparse
import shutil
import zipfile
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[1]
REF_WAVS = ['refs/Q1.wav', 'refs/Q2.wav', 'refs/Q3.wav', 'refs/Q4.wav', 'refs/neutral.wav']


def build_backend(target, refs_from):
    tts = root / 'tts-service'
    with zipfile.ZipFile(refs_from) as old, zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        missing = [name for name in REF_WAVS if name not in old.namelist()]
        if missing:
            raise SystemExit(f'{refs_from} lacks {", ".join(missing)}')
        for name in ['NOTICE.md', 'models.lock.json', 'models.py']:
            z.write(tts / name, name)
        for folder in ['licenses', 'refs', 'vendor']:
            for path in sorted((tts / folder).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    z.write(path, path.relative_to(tts).as_posix())
        for name in REF_WAVS:
            z.writestr(name, old.read(name))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', default=str(root / 'space-upload'))
    parser.add_argument('--refs-from', default=str(here / 'backend.zip'), help='an earlier backend.zip that holds refs/*.wav')
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f'{out} already exists. Move it aside before creating a new release.')
    if not Path(args.refs_from).is_file():
        raise SystemExit('The reference WAVs are needed: pass --refs-from path/to/an/earlier/backend.zip')
    if not (root / 'dist/client/index.html').is_file():
        raise SystemExit('Run pnpm build first.')
    out.mkdir(parents=True)
    for name in ['app.py', 'web_host.py', 'persistent_store.py', 'requirements.txt', 'packages.txt', 'README.md']:
        shutil.copy2(here / name, out / name)
    build_backend(out / 'backend.zip', args.refs_from)
    include = ['server', 'drizzle', 'db', 'public', 'dist', 'vendor']
    files = [p for p in root.iterdir() if p.is_file() and p.suffix in ['.js', '.mjs', '.html', '.css', '.json', '.yaml', '.ts']]
    files = [p for p in files if p.name not in ['release-manifest.json']]
    for name in include:
        files.extend(p for p in (root / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    with zipfile.ZipFile(out / 'webapp.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(set(files)):
            if path.name == 'downloads.json':
                continue
            z.write(path, path.relative_to(root).as_posix())
        # Browser models are already bundled; no author's model host is needed.
        z.writestr('downloads.json', '[]\n')
    print('Upload the contents of ' + str(out) + ' to the ECHO Space. Mount a PRIVATE bucket at /data first.')
    print('Then choose the conversation model with configure_space.py (dry run by default).')


if __name__ == '__main__':
    main()
