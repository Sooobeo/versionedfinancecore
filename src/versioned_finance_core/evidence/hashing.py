from hashlib import sha256
from pathlib import Path


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a SHA-256 digest without loading the whole file into memory."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()

