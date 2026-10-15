"""Install the bundled SynFrame skill; preserve any previous installation."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path


def install(destination):
    source=Path(__file__).resolve().parents[1]/'skills/synframe'
    destination=Path(destination).expanduser().absolute()
    if destination.is_symlink():
        raise ValueError('destination is a symlink; select an explicit directory')
    if destination.exists():
        marker=destination/'SKILL.md'
        if not marker.is_file() or not marker.read_text(encoding='utf-8').startswith('---\nname: synframe\n'):
            raise ValueError('destination is not an existing SynFrame skill')
    if source.resolve()==destination.resolve() or source.resolve() in destination.resolve().parents:
        raise ValueError('install destination must be outside source skill')
    if any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('bundled skill must contain regular files, not symlinks')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.synframe-install-',dir=destination.parent))
    backup=None
    try:
        shutil.copytree(source,staging,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        if destination.exists():
            backup=destination.parent.parent/'.synframe-backups'/uuid.uuid4().hex
            backup.parent.mkdir(parents=True,exist_ok=True)
            destination.rename(backup)
        try:staging.rename(destination)
        except BaseException:
            if backup is not None and not destination.exists():backup.rename(destination)
            raise
    finally:
        if staging.exists():shutil.rmtree(staging)
    files={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(destination.rglob('*')) if p.is_file()}
    return {'installed':str(destination),'backup':str(backup) if backup else None,'files':len(files),'sha256':files}


if __name__=='__main__':
    default=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'skills/synframe'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=default)
    args=parser.parse_args()
    print(json.dumps(install(args.destination),ensure_ascii=False,indent=2))
