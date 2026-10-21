"""Bounded-memory hashing; every call reads the entire current file."""
import hashlib
from pathlib import Path
from .schema import require


def file_sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def validate_artifacts(artifacts):
    """Check the current declared files; never rewrite files or saved hashes."""
    require(type(artifacts) is list, 'artifact_refs must be a list')
    for artifact in artifacts:
        require(type(artifact) is dict and set(artifact) == {'path', 'sha256', 'source'},
                'artifact needs path/hash/source')
        require(all(type(artifact[k]) is str and artifact[k].strip() for k in artifact),
                'artifact path/hash/source must be nonempty strings')
        path = Path(artifact['path'])
        require(path.is_absolute() and path.is_file(), 'artifact is absent: ' + str(path))
        try:
            actual = file_sha256(path)
        except OSError as exc:
            raise ValueError('artifact cannot be read: ' + str(path)) from exc
        require(actual == artifact['sha256'], 'artifact changed after validation: ' + str(path))
