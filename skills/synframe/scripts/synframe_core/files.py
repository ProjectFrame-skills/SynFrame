"""Bounded-memory hashing; every call reads the entire current file."""
import hashlib
from pathlib import Path


def file_sha256(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()
