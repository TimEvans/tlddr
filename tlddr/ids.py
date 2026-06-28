import hashlib
import re
from pathlib import Path


def doc_id(path: Path) -> str:
    stem = path.stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem)
    return slug.strip("-")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
